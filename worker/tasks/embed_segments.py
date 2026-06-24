"""
Embedding segments with OpenAI text-embedding-3-small for pgvector RAG.
Stored as JSONB float arrays — no pgvector client needed on write.
"""
import json
import os

from celery_app import app
import httpx
from sqlalchemy import text
from db import get_session

EMBEDDING_BATCH = 20
EMBEDDING_MODEL = "text-embedding-3-small"


def _get_embedding_config() -> tuple[str, str, str]:
    endpoint = os.getenv("LLM_ENDPOINT", os.getenv("AZURE_FOUNDRY_ENDPOINT", "")).rstrip("/")
    api_key = os.getenv("LLM_API_KEY", os.getenv("AZURE_FOUNDRY_KEY", ""))
    style = os.getenv("LLM_API_STYLE", "azure").lower()
    return endpoint, api_key, style


def _embed_texts(texts: list[str]) -> list[list[float]]:
    endpoint, api_key, style = _get_embedding_config()
    if not endpoint or not api_key:
        raise ValueError("LLM endpoint/key not configured for embeddings")

    if style == "azure":
        url = f"{endpoint}/openai/deployments/{EMBEDDING_MODEL}/embeddings?api-version=2024-02-01"
        headers = {"api-key": api_key, "Content-Type": "application/json"}
    else:
        url = f"{endpoint}/embeddings"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    body: dict = {"input": texts}
    if style != "azure":
        body["model"] = EMBEDDING_MODEL

    with httpx.Client(timeout=60) as client:
        r = client.post(url, headers=headers, json=body)
        r.raise_for_status()
        data = r.json()["data"]
        return [item["embedding"] for item in sorted(data, key=lambda x: x["index"])]


@app.task(name="tasks.embed_segments.embed_segments", bind=True, max_retries=2, default_retry_delay=120)
def embed_segments(self, meeting_id: str):
    """Embed all transcript segments for a meeting and store in DB."""
    try:
        with get_session() as session:
            rows = session.execute(
                text("""
                    SELECT id, text FROM transcript_segments
                    WHERE meeting_id = :mid
                    ORDER BY start_ms
                """),
                {"mid": meeting_id},
            ).fetchall()

        if not rows:
            print(f"[embed_segments] No segments for {meeting_id}", flush=True)
            return

        segment_ids = [r[0] for r in rows]
        texts = [r[1] for r in rows]

        print(f"[embed_segments] Embedding {len(texts)} segments for {meeting_id}", flush=True)

        all_embeddings = []
        for i in range(0, len(texts), EMBEDDING_BATCH):
            batch = texts[i: i + EMBEDDING_BATCH]
            try:
                embeddings = _embed_texts(batch)
                all_embeddings.extend(embeddings)
            except Exception as e:
                print(f"[embed_segments] Batch {i} failed: {e}", flush=True)
                all_embeddings.extend([None] * len(batch))

        with get_session() as session:
            for seg_id, emb in zip(segment_ids, all_embeddings):
                if emb is not None:
                    session.execute(
                        text("""
                            UPDATE transcript_segments
                            SET embedding = :emb::jsonb
                            WHERE id = :id
                        """),
                        {"emb": json.dumps(emb), "id": seg_id},
                    )
            session.commit()

        embedded_count = sum(1 for e in all_embeddings if e is not None)
        print(f"[embed_segments] Embedded {embedded_count}/{len(texts)} segments for {meeting_id}", flush=True)

    except Exception as exc:
        print(f"[embed_segments] Fatal error: {exc}", flush=True)
        raise self.retry(exc=exc)
