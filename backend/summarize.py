import json, textwrap, google.generativeai as genai
from pathlib import Path
from pydantic import ValidationError
from summary_schema import MeetingSummary, Topic
import os
from dotenv import load_dotenv

load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
MODEL = genai.GenerativeModel("gemini-2.0-flash")

SYSTEM_PROMPT = """
You are a certified NYC Community‑Board stenographer creating detailed meeting summaries.

CRITICAL REQUIREMENTS:
⟶  Return ONLY valid JSON (no markdown) that matches the schema
⟶  Create INFORMATIVE summaries that explain WHAT was discussed, not just that topics were discussed
⟶  Include SPECIFIC details: vote counts, addresses, agency names, dates, specific proposals
⟶  For each topic, explain the KEY POINTS, decisions made, and concerns raised
⟶  Speaker summaries should include WHAT they presented or discussed, not just their names
⟶  Do NOT use vague language like "various topics" or "multiple presentations"
⟶  Pull actual content from the transcript - quotes, specific requests, detailed proposals
⟶  The summary field for each topic should be 2-4 sentences explaining the substance
""".strip()

def call_gemini(system_prompt: str, user_text: str) -> str:
    # Combine system prompt and user text into a single prompt
    combined_prompt = f"{system_prompt}\n\n{user_text}"
    
    rsp = MODEL.generate_content(
        combined_prompt,
        generation_config={
            "temperature": 0.2,
            "max_output_tokens": 4096,  # Increased for more detailed summaries
        },
    )
    return rsp.text.strip()

# --- map-reduce driver -------------------------------------------------
CHUNK_LEN = 12000  # chars; ~2k tokens – safe for Flash

def chunk_text(text: str, size: int = CHUNK_LEN):
    for i in range(0, len(text), size):
        yield text[i : i + size]

def summarize_transcript(full_txt: str, meeting_date: str) -> MeetingSummary:
    """Map-reduce: 1) topic snippets per chunk, 2) combine."""
    partials = []
    
    # First pass: Extract detailed topics from each chunk
    for i, chunk in enumerate(chunk_text(full_txt)):
        chunk_prompt = f"""Analyze this Community Board meeting transcript chunk #{i+1}.

Extract detailed topics with these requirements:
- Create informative topic titles that describe WHAT is being discussed
- Write 2-4 sentence summaries explaining the SUBSTANCE of discussion
- Include specific proposals, concerns, and decisions
- Note who spoke and WHAT they said
- Include any vote counts, addresses, or specific details

Transcript chunk:
```
{chunk}
```

Return JSON array "topics" with detailed summaries following the schema."""

        system_with_schema = SYSTEM_PROMPT + f"\n\nJSON Schema:\n{json.dumps(Topic.model_json_schema(), indent=2)}"
        
        raw = call_gemini(system_with_schema, chunk_prompt)
        
        # Try to parse the response
        try:
            # If the response is wrapped in ```json blocks, extract it
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0].strip()
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0].strip()
            
            # Ensure we have a proper structure
            parsed = json.loads(raw)
            if isinstance(parsed, dict) and "topics" in parsed:
                partials.extend(parsed["topics"])
            elif isinstance(parsed, list):
                partials.extend(parsed)
            else:
                print(f"Warning: Unexpected structure in chunk {i+1}")
                
        except json.JSONDecodeError as e:
            print(f"Warning: Failed to parse chunk {i+1} response: {e}")
            continue

    # Reduce step: Consolidate into comprehensive summary
    reduce_prompt = f"""Create a COMPREHENSIVE meeting summary from these topic segments.

REQUIREMENTS:
1. Merge related topics but keep ALL substantive details
2. Create an overall summary that is 2-3 paragraphs explaining:
   - The main purpose and type of meeting
   - The KEY topics discussed with specific details
   - Major decisions, votes, or actions taken
   - Important concerns raised by the community
3. Each topic summary must explain WHAT was discussed, not just list topics
4. Include specific examples, quotes, or proposals where available
5. Attendance should specify roles and what people contributed

Meeting date: {meeting_date}

Topic segments to consolidate:
{json.dumps(partials, indent=2)}

Create a detailed, informative summary that someone who missed the meeting would find useful."""

    system_final = SYSTEM_PROMPT + f"\n\nJSON Schema:\n{json.dumps(MeetingSummary.model_json_schema(), indent=2)}"
    raw_final = call_gemini(system_final, reduce_prompt)
    
    # Clean up the response if needed
    if "```json" in raw_final:
        raw_final = raw_final.split("```json")[1].split("```")[0].strip()
    elif "```" in raw_final:
        raw_final = raw_final.split("```")[1].split("```")[0].strip()
    
    try:
        final = MeetingSummary.model_validate_json(raw_final)
        return final
    except ValidationError as e:
        print(f"Validation error: {e}")
        # Try to fix common issues
        try:
            # Parse as dict and fix any issues
            data = json.loads(raw_final)
            
            # Ensure attendance is a dict with integer values
            if "attendance" in data and isinstance(data["attendance"], dict):
                for key in data["attendance"]:
                    if isinstance(data["attendance"][key], str):
                        # Try to extract number from string
                        import re
                        numbers = re.findall(r'\d+', str(data["attendance"][key]))
                        data["attendance"][key] = int(numbers[0]) if numbers else 0
            
            # Try validation again
            final = MeetingSummary.model_validate(data)
            return final
            
        except Exception as e2:
            raise RuntimeError(f"Gemini produced invalid JSON: {e} / {e2}")