"""
Decode raw Opus frames captured via WebRTC Insertable Streams to a WAV file.

Each input file is a binary stream of records:
    [4 bytes: frame_length (LE uint32)] [N bytes: opus_packet]

The Opus packets are individual codec frames as delivered by Chromium's
RTCEncodedAudioFrame.data — typically 20 ms each at 48 kHz mono.
"""
import struct
import sys
import wave

import opuslib


SAMPLE_RATE = 48000
CHANNELS = 1
MAX_FRAME_SAMPLES = 5760  # 120 ms at 48 kHz — biggest possible Opus frame


def decode_opus_file(opus_path: str, wav_path: str) -> tuple[int, int]:
    """Decode an Opus frame stream file → WAV.

    Returns (frames_decoded, frames_failed).
    """
    decoder = opuslib.Decoder(SAMPLE_RATE, CHANNELS)
    pcm_chunks: list[bytes] = []
    decoded = 0
    failed = 0

    with open(opus_path, "rb") as fh:
        while True:
            header = fh.read(4)
            if len(header) < 4:
                break
            (length,) = struct.unpack("<I", header)
            if length == 0 or length > 10_000:
                # Sanity: skip implausible lengths.
                break
            packet = fh.read(length)
            if len(packet) < length:
                break
            try:
                pcm = decoder.decode(packet, MAX_FRAME_SAMPLES, decode_fec=False)
                pcm_chunks.append(pcm)
                decoded += 1
            except Exception:
                failed += 1
                # Insert 20 ms of silence to keep timing roughly aligned.
                pcm_chunks.append(b"\x00" * (960 * 2))

    with wave.open(wav_path, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)  # s16le
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(b"".join(pcm_chunks))

    return decoded, failed


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: opus_decoder.py <input.opus> <output.wav>", file=sys.stderr)
        sys.exit(1)
    d, f = decode_opus_file(sys.argv[1], sys.argv[2])
    print(f"decoded {d} frames, {f} failed → {sys.argv[2]}")
