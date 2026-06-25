"""
Builds context from DB and calls GPT-4o-mini for live Q&A responses.
Target: answer generated in under 800ms.
"""
import os
from foundry_client import chat_completion

GPT4OMINI = os.environ.get("AZURE_FOUNDRY_GPT4O_MINI_DEPLOYMENT", "gpt-4o-mini")

ZAPPER_SYSTEM = (
    "You are Zapper, an AI meeting participant in a live Teams call. "
    "You have access to past meeting summaries and open action items. "
    "Rules: answer in 2-4 sentences MAX (spoken aloud). Be specific. "
    "No filler phrases. Use the context provided. If you do not know, say so in one sentence."
)


async def answer_question(question: str, context: dict) -> str:
    """Build context from DB and return a concise spoken answer."""
    pending = "\n".join([
        f"- {i['assignee']}: {i['description']} (from {i['meeting_title']})"
        for i in context.get("pending_items", [])
    ]) or "No open action items"

    summaries = "\n\n".join([
        f"{s['date']} - {s['title']}:\n" + "\n".join(s.get("executive_summary", []))
        for s in context.get("recent_summaries", [])
    ]) or "No previous meetings"

    user_msg = (
        f"LIVE TRANSCRIPT (last 10 min):\n{context.get('live_transcript') or 'None yet'}\n\n"
        f"PARTICIPANTS: {', '.join(context.get('participants', []))}\n\n"
        f"OPEN ACTION ITEMS:\n{pending}\n\n"
        f"RECENT SUMMARIES:\n{summaries}\n\n"
        f"AGENDA: {context.get('agenda') or 'Not set'}\n\n"
        f"QUESTION: {question}\n\nAnswer as Zapper. Max 4 sentences."
    )
    return await chat_completion(
        model=GPT4OMINI,
        temperature=0.3,
        max_tokens=150,
        messages=[
            {"role": "system", "content": ZAPPER_SYSTEM},
            {"role": "user", "content": user_msg},
        ],
    )
