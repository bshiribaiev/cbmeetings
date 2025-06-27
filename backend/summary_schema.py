from typing import List, Literal, Dict, Optional
from pydantic import BaseModel, Field

class ActionItem(BaseModel):
    task: str
    owner: str
    due: str  # ISO date

class Decision(BaseModel):
    item: str = Field(description="What was decided")
    outcome: str = Field(description="The result of the decision")
    vote: Optional[str] = Field(description="Vote count if applicable", default=None)
    details: str = Field(description="Additional context about the decision")

class Topic(BaseModel):
    title: str
    speakers: List[str]
    summary: str = Field(description="A detailed 3-5 sentence summary explaining WHAT was discussed, key points raised, and outcomes")
    decisions: List[str]  # Keep simple for internal use
    detailed_decisions: List[Decision] = Field(default_factory=list, description="Structured decision information")
    action_items: List[ActionItem]
    sentiment: Literal["positive", "neutral", "negative"]
    # Add fields for specific details
    key_points: List[str] = Field(default_factory=list, description="Key discussion points")
    concerns_raised: List[str] = Field(default_factory=list, description="Specific concerns mentioned")
    proposals: List[str] = Field(default_factory=list, description="Specific proposals discussed")

class MeetingSummary(BaseModel):
    meeting_date: str  # ISO
    meeting_type: str = Field(description="Type of meeting (e.g., 'Land Use Committee', 'Full Board')")
    
    # Rich narrative summary - this is what you want!
    executive_summary: str = Field(
        description="A detailed 2-3 paragraph narrative summary of the meeting that reads like a news article. "
                   "Include specific names, proposals, decisions, and key discussion points. "
                   "This should give someone who wasn't there a clear understanding of what happened."
    )
    
    # Structured data
    topics: List[Topic]
    overall_sentiment: Literal["positive", "neutral", "negative"]
    attendance: Dict[str, int]  # e.g. {"board_members": 12, "public": 40}
    
    # Additional structured data for the main analysis
    key_decisions: List[Decision] = Field(default_factory=list)
    public_concerns: List[str] = Field(default_factory=list)
    next_steps: List[str] = Field(default_factory=list)
    
    # Meeting metadata
    total_decisions: int = 0
    total_action_items: int = 0
    primary_focus: str = Field(default="", description="Main focus of the meeting")