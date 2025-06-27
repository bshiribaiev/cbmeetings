import json
import google.generativeai as genai
from pydantic import ValidationError
from summary_schema import MeetingSummary, Topic, Decision
import os
from dotenv import load_dotenv
import re

load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
MODEL = genai.GenerativeModel("gemini-2.0-flash")

SYSTEM_PROMPT = """
You are an expert NYC Community Board meeting analyst creating comprehensive summaries for public records.

CRITICAL REQUIREMENTS:
1. **Executive Summary**: Write a detailed 2-3 paragraph narrative that reads like a news article. Include:
   - Specific names of presenters and their organizations
   - Exact proposals, addresses, and development details
   - Key decisions with vote counts
   - Major concerns raised by board members or the public
   - Important context about why items matter to the community

2. **Topic Summaries**: For each topic, write 3-5 sentences that explain:
   - What was specifically proposed or discussed
   - Who presented and their key arguments
   - What concerns or support was expressed
   - Any decisions made or next steps identified

3. **Specific Details**: Always include:
   - Full names and titles when first mentioned
   - Exact addresses or location descriptions
   - Specific numbers (units, square footage, percentages)
   - Vote counts and decision outcomes
   - Direct quotes when impactful

4. **Analysis Quality**:
   - Write as if for someone who needs to understand what happened without watching
   - Avoid generic phrases like "various topics were discussed"
   - Focus on substance, not just process
   - Highlight what matters to the community

Return ONLY valid JSON matching the provided schema.
""".strip()

def call_gemini(system_prompt: str, user_text: str) -> str:
    combined_prompt = f"{system_prompt}\n\n{user_text}"
    
    rsp = MODEL.generate_content(
        combined_prompt,
        generation_config={
            "temperature": 0.2,
            "max_output_tokens": 8192,
            "response_mime_type": "application/json",
        },
    )
    return rsp.text.strip()

CHUNK_LEN = 15000  

def chunk_text(text: str, size: int = CHUNK_LEN):
    """Smart chunking that tries to break at natural boundaries"""
    for i in range(0, len(text), size):
        chunk = text[i : i + size]
        
        # If not the last chunk, try to break at a sentence
        if i + size < len(text):
            last_period = chunk.rfind('. ')
            if last_period > size * 0.8:  # Only if we're past 80% of chunk
                chunk = chunk[:last_period + 1]
        
        yield chunk

def extract_meeting_type(title: str, transcript: str) -> str:
    """Extract the specific type of meeting"""
    title_lower = title.lower() if title else ""
    
    if 'full board' in title_lower:
        return "Full Board Meeting"
    elif 'land use' in title_lower:
        return "Land Use Committee Meeting"
    elif 'parks' in title_lower and 'environment' in title_lower:
        return "Parks & Environment Committee Meeting"
    elif 'transportation' in title_lower:
        return "Transportation Committee Meeting"
    elif 'business' in title_lower:
        return "Business & Consumer Issues Committee Meeting"
    elif 'housing' in title_lower:
        return "Housing Committee Meeting"
    elif 'budget' in title_lower:
        return "Budget Committee Meeting"
    
    # Check in transcript if not in title
    transcript_start = transcript[:1000].lower()
    if 'land use committee' in transcript_start:
        return "Land Use Committee Meeting"
    elif 'parks committee' in transcript_start:
        return "Parks Committee Meeting"
    
    return "Community Board Meeting"

def summarize_transcript(full_txt: str, meeting_date: str, title: str = None) -> MeetingSummary:
    """Generate a rich, detailed summary of the meeting"""
    
    meeting_type = extract_meeting_type(title, full_txt)
    chunks = list(chunk_text(full_txt))
    
    # First pass: Extract detailed information from each chunk
    chunk_summaries = []
    all_topics = []
    all_speakers = set()
    all_decisions = []
    all_concerns = []
    
    for i, chunk in enumerate(chunks):
        chunk_prompt = f"""
        Analyze this Community Board meeting transcript (chunk {i+1} of {len(chunks)}).
        
        Extract the following with MAXIMUM DETAIL:
        
        1. **Narrative Summary**: Write 2-3 paragraphs explaining what happened in this section.
           Include speaker names, specific proposals, decisions, and key discussion points.
        
        2. **Topics**: For each distinct topic discussed:
           - Title that describes the specific item (e.g., "215 West 95th Street Sidewalk Cafe Application")
           - All speakers who addressed this topic
           - Detailed 3-5 sentence summary of the discussion
           - Any decisions made with vote counts
           - Specific concerns or support expressed
           - Key proposals or requests
        
        3. **Decisions**: List any formal decisions with:
           - Exact item being decided
           - Vote count if mentioned
           - Outcome
           - Context about why it matters
        
        4. **Public Concerns**: Specific concerns raised by anyone
        
        5. **Key Quotes**: Important statements that capture the essence of discussions
        
        Transcript chunk:
        ```
        {chunk}
        ```
        
        Return JSON with structure:
        {{
            "narrative": "detailed narrative of this chunk",
            "topics": [/* list of topic objects */],
            "decisions": [/* list of decision objects */],
            "concerns": [/* list of specific concerns */],
            "speakers": [/* list of speaker names */],
            "key_quotes": [/* important quotes */]
        }}
        """
        
        try:
            raw = call_gemini(SYSTEM_PROMPT, chunk_prompt)
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0].strip()
            
            chunk_data = json.loads(raw)
            chunk_summaries.append(chunk_data.get("narrative", ""))
            
            # Collect all data
            if "topics" in chunk_data:
                all_topics.extend(chunk_data["topics"])
            if "speakers" in chunk_data:
                all_speakers.update(chunk_data["speakers"])
            if "decisions" in chunk_data:
                all_decisions.extend(chunk_data["decisions"])
            if "concerns" in chunk_data:
                all_concerns.extend(chunk_data["concerns"])
                
        except Exception as e:
            print(f"Warning: Failed to process chunk {i+1}: {e}")
            continue
    
    # Second pass: Create comprehensive summary
    consolidation_prompt = f"""
    Create a COMPREHENSIVE meeting summary from the following information.
    
    Meeting Type: {meeting_type}
    Meeting Date: {meeting_date}
    
    REQUIREMENTS:
    1. **Executive Summary**: Write 2-3 detailed paragraphs that tell the story of this meeting.
       - Start with the most important/newsworthy items
       - Include specific names, proposals, and decisions
       - Explain why items matter to the community
       - Use a narrative style that flows naturally
       - Make it informative enough that someone could understand what happened without watching
    
    2. **Consolidate Topics**: Merge related discussions into coherent topics
       - Each topic should have a specific, descriptive title
       - Include detailed summaries with concrete information
       - List all relevant speakers
       - Include decisions and action items
    
    3. **Structure Decisions**: Format all decisions with full context
    
    Here's the extracted information:
    
    Chunk Narratives:
    {json.dumps(chunk_summaries, indent=2)}
    
    All Topics:
    {json.dumps(all_topics, indent=2)}
    
    All Decisions:
    {json.dumps(all_decisions, indent=2)}
    
    All Concerns:
    {json.dumps(all_concerns, indent=2)}
    
    Speakers:
    {json.dumps(list(all_speakers), indent=2)}
    
    Create a rich, detailed summary following the MeetingSummary schema.
    The executive_summary field is the most important - make it comprehensive and informative.
    """
    
    schema_with_example = SYSTEM_PROMPT + f"""
    
    JSON Schema: {json.dumps(MeetingSummary.model_json_schema(), indent=2)}
    
    Example of a good executive_summary:
    "The Land Use Committee meeting on January 15, 2024, focused primarily on three major development proposals affecting the Upper West Side. Ida Su-Chen from the Department of City Planning presented a significant text amendment proposal for the former ABC site that would incorporate it into the Lincoln Square special district, allowing for increased housing development while maintaining some height restrictions. The proposal, which does not require mandatory inclusionary housing but encourages affordable units under current zoning, generated substantial discussion about balancing development needs with neighborhood character. Board members expressed concerns about the lack of guaranteed affordable housing and the potential precedent for future developments.
    
    The committee also reviewed a sidewalk cafe application for 215 West 95th Street, where the applicant agreed to community requests for reduced hours and improved maintenance. After extensive negotiation, the committee voted 8-2-1 to approve the application with conditions. Additionally, the Belnord's proposal to lease retail space to Chase Bank sparked debate about the concentration of banks on Broadway, though the committee ultimately voted to take no position, recognizing the as-of-right nature of the lease."
    """
    
    raw_final = call_gemini(schema_with_example, consolidation_prompt)
    
    if "```json" in raw_final:
        raw_final = raw_final.split("```json")[1].split("```")[0].strip()
    
    try:
        # Parse and enhance the data
        data = json.loads(raw_final)
        
        # Calculate totals
        total_decisions = len(data.get("key_decisions", []))
        total_action_items = sum(len(topic.get("action_items", [])) for topic in data.get("topics", []))
        
        # Add calculated fields
        data["meeting_type"] = meeting_type
        data["total_decisions"] = total_decisions
        data["total_action_items"] = total_action_items
        data["meeting_date"] = meeting_date
        
        # Ensure we have detailed decisions
        if "key_decisions" not in data:
            data["key_decisions"] = []
        
        # Extract decisions from topics if needed
        for topic in data.get("topics", []):
            if "decisions" in topic and topic["decisions"]:
                for decision in topic["decisions"]:
                    if isinstance(decision, str):
                        # Convert string decision to Decision object
                        data["key_decisions"].append({
                            "item": decision,
                            "outcome": "Decided",
                            "vote": "See transcript",
                            "details": f"Part of {topic['title']} discussion"
                        })
        
        # Ensure public_concerns is populated
        if not data.get("public_concerns") and all_concerns:
            data["public_concerns"] = all_concerns[:15]  # Top 15 concerns
        
        # Validate and return
        final = MeetingSummary.model_validate(data)
        return final
        
    except Exception as e:
        print(f"Error creating final summary: {e}")
        # Fallback with whatever we have
        return MeetingSummary(
            meeting_date=meeting_date,
            meeting_type=meeting_type,
            executive_summary=chunk_summaries[0] if chunk_summaries else "Meeting summary unavailable",
            topics=[],
            overall_sentiment="neutral",
            attendance={"estimated": len(all_speakers)},
            public_concerns=all_concerns[:10],
            total_decisions=len(all_decisions),
            total_action_items=0
        )