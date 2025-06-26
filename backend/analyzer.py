import json
import re
import logging
import difflib
import google.generativeai as genai
import os

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Union, Any
from dotenv import load_dotenv

load_dotenv()

# Configure Gemini API key
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')  

if not GEMINI_API_KEY:
    print("\nGEMINI_API_KEY not found!")
    raise ValueError("GEMINI_API_KEY environment variable is required")

logger = logging.getLogger(__name__)

@dataclass
class VoteRecord:
    item: str
    outcome: str
    vote_count: str
    vote_type: str
    context: str
    position: int
    raw_text: str
    confidence: float = 1.0

class CBAnalyzer:
    def __init__(self):
        self.cb_context = """
        CONTEXT: Community Board (CB) meetings are NYC local government meetings where:
        - Board members vote on local issues, budget priorities, and resolutions
        - Votes are recorded in formats like "11-0-1-0" (yes-no-abstain-notpresent)
        - Common vote patterns: unanimous, X to Y, X-Y-Z-W
        - Meetings follow Robert's Rules with motions, seconds, and formal votes
        - Key phrases: "motion to approve", "call the question", "vote passes"
        - Important: CB7 = Community Board 7, covering Upper West Side Manhattan
        """
        
        # Initialize Gemini
        genai.configure(api_key=GEMINI_API_KEY)
        self.gemini_model = genai.GenerativeModel('gemini-2.0-flash')
        
        # Enhanced vote patterns with named groups
        self.vote_patterns = [
            # Formal numeric votes (most reliable)
            (r'(?:committee|board)\s+vote\s+is\s+(\d{1,2}[-–]\d{1,2}[-–]\d{1,2}[-–]\d{1,2})', 'formal_vote', 0.95),
            (r'(\d{1,2}[-–]\d{1,2}[-–]\d{1,2}[-–]\d{1,2})\.?\s*(?:non[-–]?committee|committee)', 'formal_vote', 0.95),
            (r'vote:?\s+(\d{1,2}[-–]\d{1,2}[-–]\d{1,2}[-–]\d{1,2})', 'formal_vote', 0.9),
            
            # Verbal number patterns
            (r'(\w+)\s+to\s+(\w+)\s+to\s+(\w+)\s+to\s+(\w+)', 'verbal_vote', 0.85),
            (r'(\d+)\s+to\s+(\d+)\s+to\s+(\d+)\s+to\s+(\d+)', 'numeric_verbal', 0.9),
            
            # Vote results
            (r'(?:the\s+)?vote\s+passes', 'vote_passes', 0.9),
            (r'(?:the\s+)?vote\s+fails', 'vote_fails', 0.9),
            (r'motion\s+(?:is\s+)?approved', 'motion_approved', 0.85),
            (r'motion\s+(?:is\s+)?rejected', 'motion_rejected', 0.85),
            
            # Unanimous votes
            (r'unanimously?\s+(?:approved?|passed?|adopted?|supported?)', 'unanimous', 0.95),
            (r'(?:approved?|passed?|adopted?)\s+unanimously?', 'unanimous', 0.95),
            
            # Motions and resolutions
            (r'motion\s+to\s+(?:approve|support|adopt|pass)\s+([^.]+)', 'motion', 0.8),
            (r'resolution\s+to\s+(?:approve|support|adopt)\s+([^.]+)', 'resolution', 0.8),
            
            # Call the question (indicates imminent vote)
            (r'call\s+the\s+question', 'call_question', 0.7),
            (r'ready\s+for\s+the\s+vote', 'ready_vote', 0.7),
            (r'(?:the\s+)?motion\s+has\s+passed', 'motion_passed', 0.95),
        ]
        
        # Number word mapping
        self.number_words = {
            'zero': 0, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
            'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
            'eleven': 11, 'twelve': 12, 'thirteen': 13, 'fourteen': 14, 'fifteen': 15
        }
    
    def safe_extract_string(self, value: Any) -> str:
        if isinstance(value, str):
            return value
        
        elif isinstance(value, dict):
            for key in ['name', 'text', 'value', 'item', 'content']:
                if key in value and isinstance(value[key], str):
                    return value[key]
                
            return str(value)
        
        elif isinstance(value, (list, tuple)):
            return ', '.join(self.safe_extract_string(v) for v in value)
        
        else:
            return str(value)
    
    def safe_extract_list(self, value: Any) -> List[str]:
        if isinstance(value, list):
            return [self.safe_extract_string(item) for item in value]
        elif isinstance(value, str):
            return [value]
        elif isinstance(value, dict):
            return [self.safe_extract_string(value)]
        else:
            return []
    
    def analyze_cb_meeting(self, transcript: str, model: str = 'gemini', title: str = None) -> Dict:
        if title:
            self._current_title = title
        
        logger.info(f"Starting enhanced analysis of {len(transcript):,} character transcript")
        
        try:
            # Extract all votes with enhanced patterns
            vote_records = self.extract_all_votes(transcript)
            logger.info(f"Extracted {len(vote_records)} potential votes")
            
            # Identify meeting segments with vote awareness
            segments = self.identify_smart_segments(transcript, vote_records)
            logger.info(f"Identified {len(segments)} meeting segments")
            
            # Analyze each segment with context
            segment_analyses = []
            for i, segment in enumerate(segments):
                logger.info(f"Analyzing segment {i+1}/{len(segments)}: {segment['type']}")
                try:
                    analysis = self.analyze_segment_with_context(segment, model, vote_records)
                    if analysis and isinstance(analysis, dict):
                        segment_analyses.append(analysis)
                except Exception as seg_error:
                    logger.warning(f"Segment {i+1} analysis failed: {seg_error}")
            
            # Combine analyses with vote reconciliation
            combined_analysis = self.combine_analyses_smart(segment_analyses, vote_records)
            
            # Post-process and validate
            final_analysis = self.post_process_analysis(combined_analysis, transcript)
            
            logger.info("Enhanced analysis completed successfully")
            return final_analysis
            
        except Exception as e:
            logger.error(f"Enhanced analysis failed: {e}")
            import traceback
            logger.debug(f"Full error trace: {traceback.format_exc()}")
            
            # Return fallback with any votes we found
            fallback = self.create_enhanced_fallback(transcript)
            
            # If we found votes before the error, include them
            if 'vote_records' in locals() and vote_records:
                logger.info(f"Including {len(vote_records)} votes found before error")
                fallback['keyDecisions'] = []
                for vote in vote_records:
                    fallback['keyDecisions'].append({
                        "item": vote.item,
                        "outcome": vote.outcome,
                        "vote": vote.vote_count,
                        "details": f"Vote extracted from transcript (pattern: {vote.vote_type})"
                    })
            
            return fallback
    
    def combine_analyses_smart(self, analyses: List[Dict], vote_records: List[VoteRecord]) -> Dict:
        combined = {
            "summary": "",
            "keyDecisions": [],
            "publicConcerns": [],
            "nextSteps": [],
            "sentiment": "Mixed",
            "attendance": "Not specified",
            "mainTopics": [],
            "importantDates": [],
            "budgetItems": [],
            "addresses": []
        }
        
        all_topics = []
        all_concerns = []
        all_speakers = []
        all_action_items = []
        ai_decisions = []
        
        # Process segment analyses with robust type handling
        for analysis in analyses:
            if not isinstance(analysis, dict):
                continue
            
            # Extract topics safely
            topics_raw = analysis.get('main_topics', [])
            topics = self.safe_extract_list(topics_raw)
            all_topics.extend(topics)
            
            # Extract concerns safely
            concerns_raw = analysis.get('concerns', [])
            concerns = self.safe_extract_list(concerns_raw)
            all_concerns.extend(concerns)
            
            # Extract speakers safely
            speakers_raw = analysis.get('speakers', [])
            speakers = self.safe_extract_list(speakers_raw)
            all_speakers.extend(speakers)
            
            # Extract action items safely
            action_items_raw = analysis.get('action_items', [])
            action_items = self.safe_extract_list(action_items_raw)
            all_action_items.extend(action_items)
            
            # Extract decisions
            decisions = analysis.get('decisions', [])
            if isinstance(decisions, list):
                ai_decisions.extend(decisions)
        
        # Convert vote records to decision format
        for vote in vote_records:
            decision = {
                "item": vote.item,
                "outcome": vote.outcome,
                "vote": vote.vote_count,
                "details": f"Formal vote recorded. {self.extract_vote_context(vote.context)}"
            }
            combined['keyDecisions'].append(decision)
        
        # AI-detected decisions that aren't already in vote records
        for ai_decision in ai_decisions:
            if not isinstance(ai_decision, dict):
                continue
                
            # Check if this decision matches a vote record
            is_duplicate = False
            ai_item = self.safe_extract_string(ai_decision.get('item', ''))
            
            for vote_decision in combined['keyDecisions']:
                if difflib.SequenceMatcher(None, 
                    ai_item.lower(), 
                    vote_decision['item'].lower()).ratio() > 0.7:
                    # Enhance existing decision with AI context
                    ai_context = self.safe_extract_string(ai_decision.get('context', ''))
                    if ai_context:
                        vote_decision['details'] += f" {ai_context}"
                    is_duplicate = True
                    break
            
            if not is_duplicate and ai_item:
                combined['keyDecisions'].append({
                    "item": ai_item,
                    "outcome": self.safe_extract_string(ai_decision.get('outcome', 'Discussed')),
                    "vote": self.safe_extract_string(ai_decision.get('vote', 'No formal vote')),
                    "details": self.safe_extract_string(ai_decision.get('context', 'Item discussed during meeting'))
                })
        
        # Remove duplicates and limit results
        combined['publicConcerns'] = list(set(all_concerns))[:15]
        combined['nextSteps'] = self.filter_next_steps(list(set(all_action_items)))[:10]
        combined['mainTopics'] = list(set(all_topics))[:10]
        
        # Generate summary
        vote_count = len([d for d in combined['keyDecisions'] if 'vote' in d.get('details', '').lower()])
        combined['summary'] = self.generate_summary(
            len(analyses), 
            vote_count, 
            len(combined['publicConcerns']), 
            len(combined['mainTopics']),
            all_speakers
        )
        
        # Set attendance if speakers identified
        if all_speakers:
            unique_speakers = list(set(all_speakers))[:5]
            combined['attendance'] = f"Speakers included: {', '.join(unique_speakers)}"
            if len(set(all_speakers)) > 5:
                combined['attendance'] += f" and {len(set(all_speakers)) - 5} others"
        
        return combined
    
    def extract_all_votes(self, transcript: str) -> List[VoteRecord]:
        vote_records = []
        
        for pattern, vote_type, confidence in self.vote_patterns:
            matches = list(re.finditer(pattern, transcript, re.IGNORECASE))
            
            for match in matches:
                # Get extended context (1000 chars before and after)
                start = max(0, match.start() - 1000)
                end = min(len(transcript), match.end() + 1000)
                context = transcript[start:end]
                
                # Parse the vote details
                vote_details = self.parse_vote_match(match, vote_type, context)
                if vote_details:
                    vote_record = VoteRecord(
                        item=vote_details['item'],
                        outcome=vote_details['outcome'],
                        vote_count=vote_details['vote_count'],
                        vote_type=vote_type,
                        context=context,
                        position=match.start(),
                        raw_text=match.group(),
                        confidence=confidence
                    )
                    vote_records.append(vote_record)
        
        # Sort by position and remove duplicates
        vote_records.sort(key=lambda x: x.position)
        return self.deduplicate_votes(vote_records)
    
    def parse_vote_match(self, match: re.Match, vote_type: str, context: str) -> Optional[Dict]:
        if vote_type == 'formal_vote':
            vote_count = match.group(1) if match.lastindex >= 1 else match.group()
            vote_count = re.sub(r'[-–]', '-', vote_count)  # Normalize dashes
            
            # Determine what was voted on
            item = self.extract_vote_subject(context, match.start() - match.string[:match.start()].count('\n'))
            
            # Parse the vote outcome
            outcome = self.determine_outcome_from_count(vote_count)
            
            return {
                'item': item,
                'outcome': outcome,
                'vote_count': vote_count
            }
            
        elif vote_type == 'verbal_vote':
            groups = match.groups()
            numbers = []
            for g in groups:
                if g.lower() in self.number_words:
                    numbers.append(str(self.number_words[g.lower()]))
                elif g.isdigit():
                    numbers.append(g)
                else:
                    return None
            
            if len(numbers) == 4:
                vote_count = '-'.join(numbers)
                item = self.extract_vote_subject(context, match.start() - match.string[:match.start()].count('\n'))
                outcome = self.determine_outcome_from_count(vote_count)
                
                return {
                    'item': item,
                    'outcome': outcome,
                    'vote_count': vote_count
                }
                
        elif vote_type in ['vote_passes', 'motion_approved', 'unanimous']:
            item = self.extract_vote_subject(context, 0)
            return {
                'item': item,
                'outcome': 'Approved',
                'vote_count': 'Unanimous' if vote_type == 'unanimous' else 'Passed'
            }
            
        elif vote_type in ['vote_fails', 'motion_rejected']:
            item = self.extract_vote_subject(context, 0)
            return {
                'item': item,
                'outcome': 'Rejected',
                'vote_count': 'Failed'
            }
            
        elif vote_type in ['motion', 'resolution']:
            # The item is captured in the regex group
            item = match.group(1).strip() if match.lastindex >= 1 else "Board Item"
            return {
                'item': self.clean_item_text(item),
                'outcome': 'Under Consideration',
                'vote_count': 'Pending'
            }
            
        elif vote_type == 'motion_passed':
            item = self.extract_vote_subject(context, 0)
            return {
                'item': item,
                'outcome': 'Approved',
                'vote_count': 'Motion passed'
            }
            
        return None
    
    def extract_vote_subject(self, context: str, relative_pos: int) -> str:  
        context_lower = context.lower()
        
        # Look for specific application numbers or addresses
        address_match = re.search(r'(\d{1,4}\s+\w+\s+(?:avenue|street|ave|st|broadway))', context, re.IGNORECASE)
        if address_match:
            return f"Application: {address_match.group(1)}"
        
        # Look for business names
        business_patterns = [
            r'(?:for|from|by)\s+([A-Z][A-Za-z\s&]+(?:LLC|Inc|Corp|Restaurant|Cafe|Bar))',
            r'([A-Z][A-Za-z\s&]+)\s+(?:application|request|proposal)',
        ]
        for pattern in business_patterns:
            match = re.search(pattern, context)
            if match:
                return f"{match.group(1).strip()} Application"
        
        # Look for motion/resolution context
        motion_patterns = [
            r'motion\s+to\s+(\w+)\s+([^.]+?)(?:\.|,|;)',
            r'resolution\s+(?:to\s+)?(\w+)\s+([^.]+?)(?:\.|,|;)',
            r'proposal\s+to\s+(\w+)\s+([^.]+?)(?:\.|,|;)',
        ]
        for pattern in motion_patterns:
            match = re.search(pattern, context_lower)
            if match:
                action = match.group(1)
                subject = match.group(2).strip()
                return f"{action.capitalize()} {self.clean_item_text(subject)}"
        
        # Topic keywords
        topics = {
            'sidewalk cafe': 'Sidewalk Cafe Application',
            'liquor license': 'Liquor License Application',
            'outdoor dining': 'Outdoor Dining Proposal',
            'zoning': 'Zoning Matter',
            'landmark': 'Landmark Designation',
            'budget': 'Budget Item',
            'housing': 'Housing Proposal',
            'development': 'Development Application',
        }
        
        for keyword, label in topics.items():
            if keyword in context_lower:
                return label
        
        # Meeting procedure
        if 'agenda' in context_lower:
            return 'Agenda Adoption'
        elif 'minutes' in context_lower:
            return 'Minutes Approval'
        elif 'adjourn' in context_lower:
            return 'Motion to Adjourn'
        
        return 'Community Board Item'
    
    def clean_item_text(self, text: str) -> str:
        text = ' '.join(text.split())
        
        # Proper capitalization - don't capitalize articles
        words = text.split()
        if words:
            # Capitalize first word and proper nouns, but not articles/prepositions
            articles = {'the', 'a', 'an', 'of', 'in', 'on', 'at', 'to', 'for'}
            result = []
            for i, word in enumerate(words):
                if i == 0 or word.lower() not in articles:
                    result.append(word.capitalize())
                else:
                    result.append(word.lower())
            text = ' '.join(result)
        
        # Remove trailing punctuation
        text = text.rstrip('.,;:')
        
        # Limit length
        if len(text) > 100:
            text = text[:97] + '...'
        
        return text
    
    def determine_outcome_from_count(self, vote_count: str) -> str:
        if vote_count.lower() == 'unanimous':
            return 'Approved Unanimously'
        
        if '-' in vote_count:
            parts = vote_count.split('-')
            if len(parts) >= 2:
                try:
                    yes_votes = int(parts[0])
                    no_votes = int(parts[1])
                    
                    if yes_votes > no_votes:
                        if no_votes == 0:
                            return 'Approved Unanimously' if len(parts) < 3 or parts[2] == '0' else 'Approved'
                        return 'Approved'
                    elif no_votes > yes_votes:
                        return 'Rejected'
                    else:
                        return 'Tied'
                except ValueError:
                    pass
        
        return 'Recorded'
    
    def deduplicate_votes(self, votes: List[VoteRecord]) -> List[VoteRecord]:      
        if not votes:
            return []
        
        unique_votes = []
        
        for vote in votes:
            is_duplicate = False
            
            for existing in unique_votes:
                # Same position (within 200 chars)
                if abs(vote.position - existing.position) < 200:
                    # Prefer the more specific/confident one
                    if vote.confidence > existing.confidence:
                        unique_votes.remove(existing)
                    else:
                        is_duplicate = True
                        break
                
                # Similar item text
                similarity = difflib.SequenceMatcher(None, vote.item.lower(), existing.item.lower()).ratio()
                if similarity > 0.8 and vote.vote_count == existing.vote_count:
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                unique_votes.append(vote)
        
        return unique_votes
    
    def identify_smart_segments(self, transcript: str, votes: List[VoteRecord]) -> List[Dict]:
        segments = []
        
        # Create segment boundaries around votes
        boundaries = [0]
        
        for vote in votes:
            # Add boundary 1000 chars before vote (increased from 500)
            boundaries.append(max(0, vote.position - 1000))
            # Add boundary 1000 chars after vote
            boundaries.append(min(len(transcript), vote.position + 1000))
        
        boundaries.append(len(transcript))
        boundaries = sorted(set(boundaries))
        
        # Create segments from boundaries
        for i in range(len(boundaries) - 1):
            start = boundaries[i]
            end = boundaries[i + 1]
            
            # Skip very small segments (increased threshold)
            if end - start < 1000:
                continue
            
            segment_text = transcript[start:end]
            
            # Determine segment type
            segment_type = self.classify_segment_content(segment_text)
            
            # Find votes in this segment
            segment_votes = [v for v in votes if start <= v.position < end]
            
            segments.append({
                'type': segment_type,
                'text': segment_text,
                'start': start,
                'end': end,
                'votes': segment_votes
            })
        
        return segments
    
    def classify_segment_content(self, text: str) -> str:
        text_lower = text.lower()
        
        # Count indicators
        vote_indicators = len(re.findall(r'\b(vote|motion|approve|reject|unanimous)\b', text_lower))
        intro_indicators = len(re.findall(r'\b(hi|hello|good evening|thank you for|my name is)\b', text_lower))
        qa_indicators = text.count('?')
        
        if vote_indicators >= 3:
            return 'voting'
        elif intro_indicators >= 2:
            return 'presentation'
        elif qa_indicators >= 3:
            return 'discussion'
        else:
            return 'general'
    
    def analyze_segment_with_context(self, segment: Dict, model: str, all_votes: List[VoteRecord]) -> Dict:
        segment_type = segment['type']
        segment_votes = segment['votes']
        
        # Build context about votes
        vote_context = ""
        if segment_votes:
            vote_context = f"\nVotes detected in this segment:\n"
            for vote in segment_votes:
                vote_context += f"- {vote.item}: {vote.vote_count} ({vote.outcome})\n"
        
        prompt = f"""
        {self.cb_context}
        
        Analyze this {segment_type} segment from a Community Board meeting.
        {vote_context}
        
        SEGMENT TEXT:
        {segment['text'][:6000]}
        
        Extract and return a JSON object with:
        {{
            "segment_type": "{segment_type}",
            "main_topics": ["specific topics discussed"],
            "decisions": [
                {{"item": "what was decided", "context": "why/details", "vote": "if any"}}
            ],
            "concerns": ["specific concerns raised"],
            "speakers": ["names and roles if mentioned"],
            "action_items": ["follow-up items mentioned"]
        }}
        
        Focus on specific details, not general observations.
        """
        
        return self.get_ai_response(prompt, model, f"{segment_type} segment")
    
    def extract_vote_context(self, context: str) -> str:
        context_patterns = [
            r'(?:regarding|concerning|about|for)\s+([^.]+?)(?:\.|,|;)',
            r'(?:proposal|application|request)\s+(?:to|for)\s+([^.]+?)(?:\.|,|;)',
            r'(?:discussion\s+of|consideration\s+of)\s+([^.]+?)(?:\.|,|;)',
        ]
        
        for pattern in context_patterns:
            match = re.search(pattern, context, re.IGNORECASE)
            if match:
                return f"Regarding {match.group(1).strip()}"
        
        return "Vote taken after discussion"
    
    def generate_summary(self, segment_count: int, vote_count: int, concern_count: int, 
                    topic_count: int, speakers: List[str]) -> str:
        
        summary_parts = []
        
        # Try to identify meeting type from topics
        meeting_type = "Community Board meeting"
        if hasattr(self, '_current_title'):  # Store title during processing
            meeting_type = self.identify_meeting_type(self._current_title, [])
        
        summary_parts.append(meeting_type)
        
        # Add vote information
        if vote_count > 0:
            summary_parts.append(f"{vote_count} formal votes recorded")
        
        # Add topic count
        if topic_count > 0:
            summary_parts.append(f"{topic_count} main topics discussed")
        
        # Add speaker info
        if speakers:
            unique_speakers = list(set(speakers))
            if len(unique_speakers) <= 3:
                summary_parts.append(f"Presentations by {', '.join(unique_speakers)}")
            else:
                summary_parts.append(f"Multiple presentations including {', '.join(unique_speakers[:2])} and others")
        
        return ". ".join(summary_parts) + "."
    
    def post_process_analysis(self, analysis: Dict, transcript: str) -> Dict:
        # Extract any additional metadata
        if not analysis.get('importantDates'):
            dates = self.extract_dates(transcript)
            analysis['importantDates'] = dates[:5]
        
        if not analysis.get('addresses'):
            addresses = self.extract_addresses(transcript)
            analysis['addresses'] = addresses[:5]
        
        # Ensure all required fields exist
        required_fields = ['summary', 'keyDecisions', 'publicConcerns', 'nextSteps', 
                          'sentiment', 'attendance', 'mainTopics', 'importantDates', 
                          'budgetItems', 'addresses']
        
        for field in required_fields:
            if field not in analysis:
                analysis[field] = [] if field.endswith('s') else "Not specified"
        
        # Add metadata
        analysis['_metadata'] = {
            'analyzer_version': '2.1-gemini',
            'transcript_length': len(transcript),
            'word_count': len(transcript.split()),
            'analysis_timestamp': datetime.now().isoformat(),
            'ai_model': 'gemini-1.5-flash'
        }
        
        return analysis
    
    def extract_dates(self, text: str) -> List[str]:
        date_patterns = [
            r'(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}',
            r'\d{1,2}/\d{1,2}/\d{2,4}',
            r'(?:next|this|last)\s+(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)',
            r'(?:next|this|last)\s+(?:week|month|year)',
        ]
        
        dates = []
        for pattern in date_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            dates.extend(matches)
        
        return list(set(dates))
    
    def extract_addresses(self, text: str) -> List[str]:
        address_patterns = [
            r'\d{1,4}\s+\w+\s+(?:Avenue|Street|Ave|St|Place|Pl|Road|Rd|Boulevard|Blvd|Broadway)',
            r'\d{1,4}\s+(?:West|East|North|South)\s+\d{1,3}(?:st|nd|rd|th)\s+Street',
        ]
        
        addresses = []
        for pattern in address_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            addresses.extend(matches)
        
        return list(set(addresses))
    
    def get_ai_response(self, prompt: str, model: str, context: str) -> Dict:
        try:
            # Create the generation config
            generation_config = {
                "temperature": 0.1,
                "top_p": 0.9,
                "top_k": 40,
                "max_output_tokens": 8192,
                "response_mime_type": "application/json",
            }
            
            # Add system-like instructions to the prompt
            enhanced_prompt = f"""
            You are an expert analyst of NYC Community Board meetings. 
            You must respond with valid JSON only.
            
            CRITICAL: Only mark something as a "decision" if there was an ACTUAL VOTE taken.
            Discussions, suggestions, and proposals are NOT decisions unless voted on.
            
            {prompt}
            """
            
            # Generate response
            response = self.gemini_model.generate_content(
                enhanced_prompt,
                generation_config=generation_config
            )
            
            # Parse JSON response
            if response.text:
                return json.loads(response.text)
            else:
                logger.warning(f"Empty response from Gemini for {context}")
                return {"error": "Empty response"}
                
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parsing failed for {context}: {e}")
            logger.debug(f"Raw response: {response.text if 'response' in locals() else 'No response'}")
            return {"error": f"JSON parsing failed: {e}"}
        
        except Exception as e:
            logger.warning(f"Gemini analysis failed for {context}: {e}")
            return {"error": str(e)}
    
    def create_enhanced_fallback(self, transcript: str) -> Dict:
        vote_records = self.extract_all_votes(transcript)
        dates = self.extract_dates(transcript)
        addresses = self.extract_addresses(transcript)
        
        # Convert votes to decisions
        decisions = []
        for vote in vote_records[:10]:  # Limit to top 10
            decisions.append({
                "item": vote.item,
                "outcome": vote.outcome,
                "vote": vote.vote_count,
                "details": "Extracted from transcript analysis"
            })
        
        # Topic detection
        topics = []
        topic_keywords = {
            'Housing': ['housing', 'affordable', 'apartment', 'development', 'residential'],
            'Transportation': ['traffic', 'parking', 'bike', 'pedestrian', 'bus', 'subway'],
            'Business': ['restaurant', 'retail', 'commercial', 'sidewalk cafe', 'liquor license'],
            'Parks': ['park', 'playground', 'recreation', 'green space'],
            'Zoning': ['zoning', 'land use', 'permit', 'variance'],
            'Budget': ['budget', 'funding', 'allocation', 'expense'],
            'Education': ['school', 'education', 'student', 'teacher'],
            'Safety': ['safety', 'security', 'police', 'crime']
        }
        
        transcript_lower = transcript.lower()
        for topic, keywords in topic_keywords.items():
            if any(keyword in transcript_lower for keyword in keywords):
                topics.append(topic)
        
        # Build summary
        word_count = len(transcript.split())
        summary = f"Community Board meeting transcript with {word_count:,} words analyzed. "
        if vote_records:
            summary += f"Found {len(vote_records)} formal votes/decisions. "
        if topics:
            summary += f"Main topics included: {', '.join(topics[:5])}."
        
        return {
            "summary": summary,
            "keyDecisions": decisions,
            "publicConcerns": ["Enhanced analysis requires AI model for detailed concern extraction"],
            "nextSteps": ["Review full transcript for specific action items"],
            "sentiment": "Mixed",
            "attendance": f"Meeting transcript analyzed ({word_count:,} words)",
            "mainTopics": topics,
            "importantDates": dates,
            "budgetItems": [],
            "addresses": addresses,
            "_metadata": {
                "analyzer_version": "2.1-fallback",
                "transcript_length": len(transcript),
                "word_count": word_count,
                "votes_found": len(vote_records)
            }
        }
        
    def identify_meeting_type(self, title: str, topics: List[str]) -> str:
        title_lower = title.lower() if title else ""
        
        # Check title first
        if 'parks' in title_lower:
            return "Parks & Environment Committee meeting"
        elif 'business' in title_lower:
            return "Business & Consumer Issues Committee meeting"
        elif 'housing' in title_lower:
            return "Housing Committee meeting"
        elif 'transportation' in title_lower:
            return "Transportation Committee meeting"
        elif 'land use' in title_lower:
            return "Land Use Committee meeting"
        elif 'full board' in title_lower:
            return "Full Board meeting"
        
        # Check topics if title doesn't help
        topic_str = ' '.join(topics).lower()
        if 'parks' in topic_str or 'environment' in topic_str:
            return "Parks & Environment Committee meeting"
        elif 'business' in topic_str or 'restaurant' in topic_str:
            return "Business Committee meeting"
        
        return "Community Board meeting"

    def filter_next_steps(self, raw_next_steps: List[str]) -> List[str]:
        filtered = []
        
        # Keywords that indicate actual action items
        action_keywords = ['contact', 'visit', 'pick up', 'submit', 'attend', 
                          'review', 'send', 'register', 'apply', 'email', 'call']
        
        # Keywords that indicate past events or non-actions
        exclude_keywords = ['presented', 'discussed', 'was', 'were', 'received', 
                           'gave', 'showed', 'explained']
        
        for step in raw_next_steps:
            step_lower = step.lower()
            
            # Check if it's an actual action
            has_action = any(keyword in step_lower for keyword in action_keywords)
            has_exclude = any(keyword in step_lower for keyword in exclude_keywords)
            
            if has_action and not has_exclude:
                filtered.append(step)
            elif step_lower.startswith(('to ', 'please ', 'will ', 'should ')):
                filtered.append(step)
        
        return filtered