import json, textwrap, google.generativeai as genai
from pathlib import Path
from pydantic import ValidationError
from summary_schema import MeetingSummary, Topic
import os
from dotenv import load_dotenv

load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
MODEL = genai.GenerativeModel("gemini-2.0-flash")

SYSTEM_PROMPT = textwrap.dedent("""
You are an expert municipal-meeting analyst. 
Return ONLY valid JSON that conforms to the schema the user supplies. 
Do not wrap it in markdown or code fences.

Schema:
{schema}
""").strip()

def call_gemini(system_prompt: str, user_text: str) -> str:
    rsp = MODEL.generate_content(
        [{"role": "system", "text": system_prompt},
         {"role": "user",   "text": user_text}],
        generation_config={"temperature": 0.2, "max_output_tokens": 2048},
    )
    return rsp.text.strip()

# --- map-reduce driver -------------------------------------------------
CHUNK_LEN = 8000  # chars; ~2k tokens – safe for Flash

def chunk_text(text: str, size: int = CHUNK_LEN):
    for i in range(0, len(text), size):
        yield text[i : i + size]

def summarize_transcript(full_txt: str, meeting_date: str) -> MeetingSummary:
    """Map-reduce: 1) topic snippets per chunk, 2) combine."""
    partials = []
    for chunk in chunk_text(full_txt):
        prompt = f"""Transcript chunk:\n```\n{chunk}\n```\n
Return JSON array "topics" summarising this chunk."""
        raw = call_gemini(
            SYSTEM_PROMPT.format(schema=json.dumps(Topic.model_json_schema(), indent=2)),
            prompt)
        partials.append(json.loads(raw))

    # reduce step: feed concatenated topic arrays to final prompt
    reduce_prompt = f"""Consolidate the following topic arrays into a single
meeting-level summary. Meeting date: {meeting_date}

Topic arrays:
{json.dumps(partials, indent=2)}
"""
    raw_final = call_gemini(
        SYSTEM_PROMPT.format(schema=json.dumps(MeetingSummary.model_json_schema(), indent=2)),
        reduce_prompt)
    try:
        final = MeetingSummary.model_validate_json(raw_final)
    except ValidationError as e:
        # minimal retry – you can add exponential back-off
        raise RuntimeError(f"Gemini produced invalid JSON: {e}")

    return final
