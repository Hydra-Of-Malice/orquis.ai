"""
Creates an isolated Xvfb display + PulseAudio environment per bot slot.
Runs PulseAudio in foreground subprocess mode (not daemon) so it works in Docker.
"""
import os
import subprocess
import sys
import time
from dataclasses import dataclass


@dataclass
class BotEnvironment:
    slot: int
    display_num: int
    pulse_socket: str
    sink_name: str
    _pulse_proc: object = None  # subprocess.Popen handle


def create_bot_environment(slot: int) -> BotEnvironment:
    display_num = 99 + slot
    pulse_socket = f"/tmp/pulse-zapper-{slot}.sock"
    sink_name = f"zapper_sink_{slot}"

    _start_xvfb(display_num)
    pulse_proc = _start_pulseaudio(slot, pulse_socket, sink_name)

    env = BotEnvironment(
        slot=slot,
        display_num=display_num,
        pulse_socket=pulse_socket,
        sink_name=sink_name,
    )
    env._pulse_proc = pulse_proc
    return env


def _start_xvfb(display_num: int):
    # Clean up stale locks from previous unclean shutdowns
    try:
        if os.path.exists(f"/tmp/.X{display_num}-lock"):
            os.remove(f"/tmp/.X{display_num}-lock")
        if os.path.exists(f"/tmp/.X11-unix/X{display_num}"):
            os.remove(f"/tmp/.X11-unix/X{display_num}")
    except Exception:
        pass

    env = os.environ.copy()
    subprocess.Popen(
        ["Xvfb", f":{display_num}", "-screen", "0", "1920x1080x24", "-ac"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(1)
    print(f"[audio_setup] Xvfb started on :{display_num}", file=sys.stderr)


def _start_pulseaudio(slot: int, socket_path: str, sink_name: str):
    config_dir = f"/tmp/pulse-config-{slot}"
    os.makedirs(config_dir, exist_ok=True)

    # If a PulseAudio is already running for this slot AND its socket responds
    # to pactl, reuse it. Recreating it would just hit "Daemon already running".
    if os.path.exists(socket_path):
        try:
            check = subprocess.run(
                ["pactl", "--server", f"unix:{socket_path}", "info"],
                capture_output=True, text=True, timeout=5,
            )
            if check.returncode == 0:
                print(f"[audio_setup] Reusing existing PulseAudio for slot {slot}", file=sys.stderr)
                # Make sure our null-sink still exists (PulseAudio may have been
                # restarted by another path); load it idempotently.
                subprocess.run(
                    ["pactl", "--server", f"unix:{socket_path}",
                     "load-module", "module-null-sink",
                     f"sink_name={sink_name}",
                     "sink_properties=device.description=ZapperSink"],
                    capture_output=True, timeout=5,
                )
                return None  # not our process to manage
        except Exception:
            pass  # fall through to forced restart

    # Otherwise: kill any stale PulseAudio bound to this slot's config dir and
    # remove its PID file so a fresh daemon can start cleanly.
    try:
        subprocess.run(
            ["pkill", "-f", f"pulseaudio.*pulse-config-{slot}"],
            capture_output=True, timeout=5,
        )
        time.sleep(0.5)
    except Exception:
        pass
    for stale in (
        socket_path,
        f"{config_dir}/.config/pulse",  # runtime dir w/ pidfile
    ):
        try:
            if os.path.isdir(stale):
                subprocess.run(["rm", "-rf", stale], timeout=5)
            elif os.path.exists(stale):
                os.remove(stale)
        except Exception:
            pass

    # Write per-slot pulse config
    pa_config = f"""
load-module module-null-sink sink_name={sink_name} sink_properties=device.description=ZapperSink
load-module module-native-protocol-unix socket={socket_path} auth-anonymous=1 auth-cookie-enabled=0
set-default-sink {sink_name}
set-default-source {sink_name}.monitor
"""
    config_file = f"{config_dir}/default.pa"
    with open(config_file, "w") as f:
        f.write(pa_config)

    log_file = f"{config_dir}/pulseaudio.log"
    env = os.environ.copy()
    env["HOME"] = config_dir
    # Unset D-Bus to avoid daemon-mode failures in Docker
    env.pop("DBUS_SESSION_BUS_ADDRESS", None)

    # Check what flags this PulseAudio version supports
    try:
        help_out = subprocess.run(
            ["pulseaudio", "--help"], capture_output=True, text=True, timeout=5
        )
        help_text = help_out.stdout + help_out.stderr
        has_runtime_path = "--runtime-path" in help_text
        has_state_dir = "--state-dir" in help_text
        print(f"[audio_setup] PulseAudio --runtime-path supported: {has_runtime_path}", file=sys.stderr)
        print(f"[audio_setup] PulseAudio --state-dir supported: {has_state_dir}", file=sys.stderr)
    except Exception:
        has_runtime_path = False
        has_state_dir = False

    cmd = [
        "pulseaudio",
        "--daemonize=no",
        "-n",
        "-F", config_file,
        "--exit-idle-time=-1",
        "--log-level=info",
    ]
    if has_runtime_path:
        cmd.append(f"--runtime-path={config_dir}")
    if has_state_dir:
        cmd.append(f"--state-dir={config_dir}")

    print(f"[audio_setup] Starting PulseAudio: {' '.join(cmd)}", file=sys.stderr)
    proc = subprocess.Popen(
        cmd,
        env=env,
        stdout=open(log_file, "w"),
        stderr=subprocess.STDOUT,
    )

    # Wait up to 15s for socket to appear
    for i in range(15):
        if os.path.exists(socket_path):
            print(f"[audio_setup] PulseAudio socket ready after {i+1}s: {socket_path}", file=sys.stderr)
            return proc
        if proc.poll() is not None:
            # Died — dump log
            try:
                log_content = open(log_file).read()[-2000:]
            except Exception:
                log_content = "(no log)"
            print(f"[audio_setup] PulseAudio died! exit={proc.returncode}\n{log_content}", file=sys.stderr)
            return proc
        time.sleep(1)

    print(f"[audio_setup] PulseAudio socket not ready after 15s — log follows:", file=sys.stderr)
    try:
        print(open(log_file).read()[-2000:], file=sys.stderr)
    except Exception:
        pass
    return proc
