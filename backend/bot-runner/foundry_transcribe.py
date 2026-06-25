"""
Single-clip Whisper transcription via Azure AI Foundry.

Used by two callers:
  * wake-word Q&A — short utterance, text only (target < 300ms).
  * live transcription (live_context.py) — rolling chunks that optionally
    pin a meeting-level language and/or read back the detected language so
    the language tracker can stop re-detecting on every chunk.
"""
import asyncio
import os
import httpx
import sys

ENDPOINT = os.environ.get("AZURE_FOUNDRY_ENDPOINT", "")
KEY = os.environ.get("AZURE_FOUNDRY_KEY", "")
WHISPER_DEPLOYMENT = os.environ.get("AZURE_FOUNDRY_WHISPER_DEPLOYMENT", "whisper")
API_VERSION = "2024-02-01"

# Whisper sometimes returns the language as its English name ("hindi")
# rather than the ISO-639-1 code ("hi") the API expects on the next call.
_LANG_NAME_TO_ISO = {
    "afrikaans": "af", "amharic": "am", "arabic": "ar", "assamese": "as",
    "azerbaijani": "az", "bashkir": "ba", "belarusian": "be",
    "bulgarian": "bg", "bengali": "bn", "tibetan": "bo", "breton": "br",
    "bosnian": "bs", "catalan": "ca", "czech": "cs", "welsh": "cy",
    "danish": "da", "german": "de", "greek": "el", "english": "en",
    "spanish": "es", "estonian": "et", "basque": "eu", "persian": "fa",
    "finnish": "fi", "faroese": "fo", "french": "fr", "galician": "gl",
    "gujarati": "gu", "hausa": "ha", "hawaiian": "haw", "hebrew": "he",
    "hindi": "hi", "croatian": "hr", "haitian": "ht",
    "haitian creole": "ht", "hungarian": "hu", "armenian": "hy",
    "indonesian": "id", "icelandic": "is", "italian": "it",
    "japanese": "ja", "javanese": "jw", "georgian": "ka", "kazakh": "kk",
    "khmer": "km", "kannada": "kn", "korean": "ko", "latin": "la",
    "luxembourgish": "lb", "lingala": "ln", "lao": "lo",
    "lithuanian": "lt", "latvian": "lv", "malagasy": "mg", "maori": "mi",
    "macedonian": "mk", "malayalam": "ml", "mongolian": "mn",
    "marathi": "mr", "malay": "ms", "maltese": "mt", "burmese": "my",
    "nepali": "ne", "dutch": "nl", "norwegian nynorsk": "nn",
    "norwegian": "no", "occitan": "oc", "punjabi": "pa", "polish": "pl",
    "pashto": "ps", "portuguese": "pt", "romanian": "ro", "russian": "ru",
    "sanskrit": "sa", "sindhi": "sd", "sinhala": "si", "slovak": "sk",
    "slovenian": "sl", "shona": "sn", "somali": "so", "albanian": "sq",
    "serbian": "sr", "sundanese": "su", "swedish": "sv", "swahili": "sw",
    "tamil": "ta", "telugu": "te", "tajik": "tg", "thai": "th",
    "turkmen": "tk", "tagalog": "tl", "turkish": "tr", "tatar": "tt",
    "ukrainian": "uk", "urdu": "ur", "uzbek": "uz", "vietnamese": "vi",
    "yiddish": "yi", "yoruba": "yo", "chinese": "zh",
    "mandarin": "zh", "cantonese": "yue",
}


def normalize_lang(lang):
    """Coerce whatever Whisper returned into a 2-3 letter ISO code, or None."""
    if not lang:
        return None
    s = str(lang).strip().lower()
    if not s:
        return None
    if 2 <= len(s) <= 3 and s.isalpha():
        return s
    return _LANG_NAME_TO_ISO.get(s)


async def transcribe_question(wav_bytes: bytes, language: str | None = None,
                              return_language: bool = False):
    """Transcribe a single short audio clip.

    Args:
        wav_bytes: WAV-encoded audio.
        language: optional ISO code to pin the language (stabilizes output).
        return_language: when True, returns ``(text, detected_lang)`` using a
            verbose response; otherwise returns just the text string.
    """
    url = f"{ENDPOINT}openai/deployments/{WHISPER_DEPLOYMENT}/audio/transcriptions?api-version={API_VERSION}"
    data = {"response_format": "verbose_json" if return_language else "text"}
    if language:
        data["language"] = language

    max_retries = 3
    for attempt in range(max_retries):
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                url,
                headers={"api-key": KEY},
                files={"file": ("audio.wav", wav_bytes, "audio/wav")},
                data=data,
            )
            if r.status_code == 429 and attempt < max_retries - 1:
                wait_time = 2 ** attempt
                print(f"[transcribe_question] HTTP 429, retrying in {wait_time}s...", file=sys.stderr)
                await asyncio.sleep(wait_time)
                continue
            r.raise_for_status()
            
            if return_language:
                body = r.json()
                text = (body.get("text") or "").strip()
                lang = normalize_lang(body.get("language"))
                return text, lang
            return r.text.strip()
