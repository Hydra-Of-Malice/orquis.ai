"""
Speaker matching via voice fingerprinting + DOM names + participant list.
Ported core logic from zapper/worker/tasks/match_speakers.py.
"""
import glob
import json
import os
import re

import numpy as np
from sqlalchemy import text
from db import get_session

MATCH_THRESHOLD = float(os.getenv("VOICE_MATCH_THRESHOLD", "0.70"))
MIN_TRACK_BYTES = 50 * 1024

_EPHEMERAL_PATTERN = re.compile(r"^Speaker_[A-Z]$")
_UNKNOWN_PATTERN = re.compile(r"^unknown\s*\d+$", re.IGNORECASE)


def _is_ephemeral(sid: str) -> bool:
    return bool(_EPHEMERAL_PATTERN.match(sid or ""))


def _nat_sort_key(path: str) -> list:
    return [int(c) if c.isdigit() else c for c in re.split(r"(\d+)", os.path.basename(path))]


def _track_wav_for_label(rec_dir: str, label: str) -> str | None:
    if not rec_dir or not _is_ephemeral(label):
        return None
    track_wavs = sorted(glob.glob(os.path.join(rec_dir, "audio_js_t*.wav")), key=_nat_sort_key)
    track_wavs = [w for w in track_wavs if os.path.getsize(w) >= MIN_TRACK_BYTES]
    idx = ord(label[-1]) - ord("A")
    return track_wavs[idx] if 0 <= idx < len(track_wavs) else None


def _speaker_label_to_track_id(rec_dir: str, label: str) -> str | None:
    if not rec_dir or not _is_ephemeral(label):
        return None
    track_wavs = sorted(glob.glob(os.path.join(rec_dir, "audio_js_t*.wav")), key=_nat_sort_key)
    track_wavs = [w for w in track_wavs if os.path.getsize(w) >= MIN_TRACK_BYTES]
    idx = ord(label[-1]) - ord("A")
    if 0 <= idx < len(track_wavs):
        basename = os.path.basename(track_wavs[idx])
        return basename.replace("audio_js_", "").replace(".wav", "")
    return None


def _load_track_names(rec_dir: str) -> dict[str, str]:
    path = os.path.join(rec_dir, "track_names.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            data = json.load(f)
        return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str) and v.strip()}
    except Exception:
        return {}


def _load_org_profiles(session, org_id: str | None) -> list[dict]:
    rows = session.execute(
        text("""
            SELECT id, display_name, embedding, sample_count
            FROM speaker_profiles
            WHERE embedding IS NOT NULL
              AND (org_id IS NULL OR org_id = :org_id)
        """),
        {"org_id": org_id},
    ).fetchall()
    out = []
    for r in rows:
        emb = r[2]
        if isinstance(emb, str):
            try:
                emb = json.loads(emb)
            except Exception:
                continue
        if not emb:
            continue
        out.append({
            "id": r[0],
            "display_name": r[1],
            "embedding": np.asarray(emb, dtype=np.float32),
            "sample_count": int(r[3] or 0),
        })
    return out


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def _compute_embedding(wav_path: str) -> np.ndarray | None:
    """Compute ECAPA-TDNN embedding from a WAV file via SpeechBrain."""
    try:
        import torchaudio
        import torch
        cache_dir = os.getenv("SPEECHBRAIN_CACHE_DIR", "/data/models/speechbrain")
        from speechbrain.pretrained import SpeakerRecognition
        verification = SpeakerRecognition.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb",
            savedir=cache_dir,
            run_opts={"device": "cpu"},
        )
        signal, fs = torchaudio.load(wav_path)
        if fs != 16000:
            signal = torchaudio.functional.resample(signal, fs, 16000)
        signal = signal.mean(dim=0, keepdim=True)  # mono
        with torch.no_grad():
            embedding = verification.encode_batch(signal)
        return embedding.squeeze().cpu().numpy()
    except Exception as exc:
        print(f"[match_speakers] _compute_embedding failed for {wav_path}: {exc}", flush=True)
        return None


def _best_match(embedding: np.ndarray, profiles: list[dict], taken: set) -> tuple:
    best, best_sim = None, -1.0
    for p in profiles:
        if p["id"] in taken:
            continue
        sim = _cosine_similarity(embedding, p["embedding"])
        if sim > best_sim:
            best_sim, best = sim, p
    if best is None or best_sim < MATCH_THRESHOLD:
        return None, best_sim
    return best, best_sim


def _save_attributed_segments(meeting_id: str, attributed: list[dict]):
    """Replace existing segments with attributed ones."""
    with get_session() as session:
        session.execute(
            text("DELETE FROM transcript_segments WHERE meeting_id = :id"),
            {"id": meeting_id},
        )
        for seg in attributed:
            session.execute(
                text("""
                    INSERT INTO transcript_segments
                        (id, meeting_id, speaker_name, speaker_id,
                         start_ms, end_ms, text, confidence)
                    VALUES
                        (gen_random_uuid(), :meeting_id, :speaker_name, :speaker_id,
                         :start_ms, :end_ms, :text, :confidence)
                """),
                {
                    "meeting_id": meeting_id,
                    "speaker_name": seg.get("speaker_name", "Unknown"),
                    "speaker_id": seg.get("diarized_speaker_id") or seg.get("speaker_id"),
                    "start_ms": seg.get("start_ms") or seg.get("offset_ms", 0),
                    "end_ms": seg.get("end_ms") or (
                        seg.get("offset_ms", 0) + seg.get("duration_ms", 0)
                    ),
                    "text": seg.get("text", ""),
                    "confidence": seg.get("confidence"),
                },
            )
        session.commit()


def _save_track_metadata(meeting_id: str, track_meta: dict, segments: list[dict]):
    """Persist track→speaker mapping to meeting_speaker_tracks table."""
    with get_session() as session:
        session.execute(
            text("DELETE FROM meeting_speaker_tracks WHERE meeting_id = :id"),
            {"id": meeting_id},
        )
        for track_label, meta in track_meta.items():
            emb = meta.get("embedding")
            emb_json = json.dumps(emb.tolist() if hasattr(emb, "tolist") else emb) if emb is not None else None
            duration = sum(
                s.get("duration_ms", 0)
                for s in segments
                if s.get("speaker_id") == track_label
            )
            session.execute(
                text("""
                    INSERT INTO meeting_speaker_tracks
                        (id, meeting_id, track_label, assigned_name, matched_profile_id,
                         confidence, embedding, duration_ms, source, created_at)
                    VALUES
                        (gen_random_uuid(), :meeting_id, :track_label, :name,
                         :profile_id, :confidence, CAST(:embedding AS jsonb),
                         :duration_ms, :source, now())
                """),
                {
                    "meeting_id": meeting_id,
                    "track_label": track_label,
                    "name": meta.get("name", "Unknown"),
                    "profile_id": meta.get("profile_id"),
                    "confidence": meta.get("confidence"),
                    "embedding": emb_json,
                    "duration_ms": duration,
                    "source": meta.get("source", "unknown"),
                },
            )
        session.commit()


def _update_matched_profiles(track_meta: dict):
    """Update running-mean voice embeddings for matched profiles."""
    for track_label, meta in track_meta.items():
        profile_id = meta.get("profile_id")
        embedding = meta.get("embedding")
        if not profile_id or embedding is None:
            continue
        try:
            with get_session() as session:
                row = session.execute(
                    text("SELECT embedding, sample_count FROM speaker_profiles WHERE id = :id"),
                    {"id": profile_id},
                ).fetchone()
                if not row:
                    continue
                old_emb_raw = row[0]
                old_count = int(row[1] or 1)
                old_emb = np.asarray(json.loads(old_emb_raw) if isinstance(old_emb_raw, str) else old_emb_raw, dtype=np.float32)
                # Running mean
                new_count = old_count + 1
                new_emb = (old_emb * old_count + embedding) / new_count
                new_emb = new_emb / np.linalg.norm(new_emb)  # re-normalize
                session.execute(
                    text("""
                        UPDATE speaker_profiles
                        SET embedding = CAST(:emb AS jsonb),
                            sample_count = :count,
                            last_seen_at = now()
                        WHERE id = :id
                    """),
                    {"emb": json.dumps(new_emb.tolist()), "count": new_count, "id": profile_id},
                )
                session.commit()
        except Exception as exc:
            print(f"[match_speakers] Profile update failed for {profile_id}: {exc}", flush=True)


def match_speakers(meeting_id: str, segments: list[dict]) -> list[dict]:
    """Attribute segments to real speaker names. Returns enriched segment list."""
    if not segments:
        return segments

    with get_session() as session:
        row = session.execute(
            text("SELECT wav_path, org_id, participant_names FROM meetings WHERE id = :id"),
            {"id": meeting_id},
        ).fetchone()

    if not row:
        return segments

    wav_path, org_id, participant_names = row
    bot_names = {
        os.getenv("BOT_DISPLAY_NAME", "Zapper Recorder").strip().lower(),
        "zapper recorder",
    }

    rec_dir = os.path.dirname(wav_path) if wav_path and not wav_path.startswith("http") else ""
    seen_order = []
    for seg in segments:
        sid = seg.get("speaker_id", "Unknown")
        if sid not in seen_order:
            seen_order.append(sid)

    all_ephemeral = bool(seen_order) and all(_is_ephemeral(sid) for sid in seen_order)
    speaker_map: dict[str, str] = {}
    track_meta: dict[str, dict] = {}

    if all_ephemeral:
        # Step 1: DOM-resolved track names (primary source)
        dom_track_names = _load_track_names(rec_dir)
        dom_assigned: set[str] = set()

        if dom_track_names:
            unique_names = set(dom_track_names.values())
            if len(unique_names) == 1 and len(dom_track_names) > 1:
                dom_track_names = {}  # All same name = DOM mis-attribution
            else:
                for sid in seen_order:
                    track_id = _speaker_label_to_track_id(rec_dir, sid)
                    name = dom_track_names.get(track_id) if track_id else None
                    if name:
                        speaker_map[sid] = name
                        track_meta[sid] = {"name": name, "embedding": None, "confidence": 1.0, "profile_id": None, "source": "dom"}
                        dom_assigned.add(sid)
                        print(f"[match_speakers] {sid}: DOM name '{name}'", flush=True)

        # Step 2: Voice embeddings for unresolved tracks
        unresolved = [sid for sid in seen_order if sid not in dom_assigned]
        if unresolved:
            with get_session() as session:
                profiles = _load_org_profiles(session, org_id)

            taken: set = set()
            unknown_counter = 0

            for sid in unresolved:
                wav = _track_wav_for_label(rec_dir, sid)
                embedding = _compute_embedding(wav) if wav else None

                if embedding is None:
                    unknown_counter += 1
                    name = f"Unknown {unknown_counter}"
                    speaker_map[sid] = name
                    track_meta[sid] = {"name": name, "embedding": None, "confidence": None, "profile_id": None, "source": "unknown"}
                    print(f"[match_speakers] {sid}: no embedding → {name}", flush=True)
                    continue

                profile, sim = _best_match(embedding, profiles, taken)
                if profile is None:
                    unknown_counter += 1
                    name = f"Unknown {unknown_counter}"
                    speaker_map[sid] = name
                    track_meta[sid] = {"name": name, "embedding": embedding, "confidence": sim if sim > -1.0 else None, "profile_id": None, "source": "voice_unmatched"}
                    print(f"[match_speakers] {sid}: sim={sim:.3f} < {MATCH_THRESHOLD:.2f} → {name}", flush=True)
                else:
                    name = profile["display_name"]
                    speaker_map[sid] = name
                    taken.add(profile["id"])
                    track_meta[sid] = {"name": name, "embedding": embedding, "confidence": sim, "profile_id": profile["id"], "source": "voice"}
                    print(f"[match_speakers] {sid}: matched '{name}' (sim={sim:.3f})", flush=True)

        # Step 3: Participant-name fallback
        cleaned_participants = [
            n for n in (participant_names or [])
            if n and n.strip().lower() not in bot_names and "zapper" not in n.strip().lower()
        ]
        if cleaned_participants:
            taken_names = {v for v in speaker_map.values() if not _UNKNOWN_PATTERN.match(v)}
            leftover = [n for n in cleaned_participants if n not in taken_names]
            unmatched = [sid for sid in seen_order if _UNKNOWN_PATTERN.match(speaker_map.get(sid, ""))]
            if leftover and len(unmatched) == len(leftover):
                for sid, name in zip(unmatched, leftover):
                    speaker_map[sid] = name
                    track_meta[sid]["name"] = name
                    track_meta[sid]["source"] = "participant_list"
                    print(f"[match_speakers] {sid}: participant fallback → '{name}'", flush=True)
    else:
        for i, sid in enumerate(seen_order, start=1):
            speaker_map[sid] = sid if not _is_ephemeral(sid) else f"Speaker {i}"
            track_meta[sid] = {"name": speaker_map[sid], "embedding": None, "confidence": None, "profile_id": None, "source": "passthrough"}

    attributed = [
        {**seg, "speaker_name": speaker_map.get(seg.get("speaker_id", "Unknown"), "Unknown"), "diarized_speaker_id": seg.get("speaker_id", "Unknown")}
        for seg in segments
    ]

    _save_attributed_segments(meeting_id, attributed)
    _save_track_metadata(meeting_id, track_meta, segments)
    _update_matched_profiles(track_meta)
    return attributed
