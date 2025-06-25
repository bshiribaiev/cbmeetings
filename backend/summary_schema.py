from typing import List, Literal, Dict
from pydantic import BaseModel

class ActionItem(BaseModel):
    task: str
    owner: str
    due: str  # ISO date

class Topic(BaseModel):
    title: str
    speakers: List[str]
    summary: str
    decisions: List[str]
    action_items: List[ActionItem]
    sentiment: Literal["positive", "neutral", "negative"]

class MeetingSummary(BaseModel):
    meeting_date: str  # ISO
    topics: List[Topic]
    overall_sentiment: Literal["positive", "neutral", "negative"]
    attendance: Dict[str, int]  # e.g. {"board_members": 12, "public": 40}
