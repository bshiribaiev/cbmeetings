from summary_schema import MeetingSummary

def md_from_summary(ms: MeetingSummary) -> str:
    lines = []
    
    # Header
    lines.append(f"# Community Board Meeting — {ms.meeting_date}")
    lines.append("")
    
    # Overall meeting summary (if available as a custom field)
    # We'll construct a detailed summary from the topics
    lines.append("## Meeting Overview")
    
    # Create a comprehensive overview
    if ms.topics:
        overview_parts = []
        
        # Determine meeting type from topics
        topic_titles = [t.title.lower() for t in ms.topics]
        if any("budget" in t or "fiscal" in t for t in topic_titles):
            meeting_type = "budget and fiscal planning"
        elif any("parks" in t or "environment" in t for t in topic_titles):
            meeting_type = "Parks & Environment Committee"
        elif any("housing" in t or "development" in t for t in topic_titles):
            meeting_type = "housing and development"
        else:
            meeting_type = "Community Board"
        
        overview_parts.append(f"This {meeting_type} meeting covered {len(ms.topics)} main areas of discussion.")
        
        # Summarize key topics with details
        key_topics = []
        for topic in ms.topics[:3]:  # First 3 topics
            if topic.decisions:
                key_topics.append(f"{topic.title} (with {len(topic.decisions)} decisions)")
            else:
                key_topics.append(topic.title)
        
        if key_topics:
            overview_parts.append(f"Primary focus areas included: {', '.join(key_topics)}.")
        
        # Add speaker information with context
        all_speakers = []
        for topic in ms.topics:
            all_speakers.extend(topic.speakers)
        unique_speakers = list(set(all_speakers))
        
        if unique_speakers:
            if len(unique_speakers) <= 5:
                overview_parts.append(f"Key participants included {', '.join(unique_speakers[:3])}, who presented on various agenda items.")
            else:
                overview_parts.append(f"The meeting featured presentations from {len(unique_speakers)} speakers including board members, committee chairs, and community representatives.")
        
        # Add decision summary
        total_decisions = sum(len(t.decisions) for t in ms.topics)
        total_actions = sum(len(t.action_items) for t in ms.topics)
        
        if total_decisions > 0 or total_actions > 0:
            decision_text = []
            if total_decisions > 0:
                decision_text.append(f"{total_decisions} decisions were made")
            if total_actions > 0:
                decision_text.append(f"{total_actions} action items were assigned")
            overview_parts.append(f"During the meeting, {' and '.join(decision_text)}.")
        
        lines.append(" ".join(overview_parts))
    
    lines.append("")
    
    # Meeting stats
    lines.append(f"**Overall Sentiment:** {ms.overall_sentiment.title()}")
    lines.append(f"**Attendance:** {format_attendance(ms.attendance)}")
    lines.append("")
    
    # Detailed topic sections
    for i, topic in enumerate(ms.topics, 1):
        lines.append(f"## {i}. {topic.title}")
        lines.append("")
        
        # Topic metadata
        if topic.speakers:
            lines.append(f"**Speakers:** {', '.join(topic.speakers)}")
        lines.append(f"**Sentiment:** {topic.sentiment.title()}")
        lines.append("")
        
        # Topic summary - should be detailed
        lines.append("### Summary")
        lines.append(topic.summary)
        lines.append("")
        
        # Decisions with details
        if topic.decisions:
            lines.append("### Decisions")
            for decision in topic.decisions:
                lines.append(f"- {decision}")
            lines.append("")
        
        # Action items with full details
        if topic.action_items:
            lines.append("### Action Items")
            for ai in topic.action_items:
                lines.append(f"- **{ai.task}**")
                lines.append(f"  - Owner: {ai.owner}")
                lines.append(f"  - Due: {ai.due}")
            lines.append("")
    
    return "\n".join(lines)

def format_attendance(attendance: dict) -> str:
    """Format attendance information in a readable way"""
    if not attendance:
        return "Not specified"
    
    parts = []
    for key, value in attendance.items():
        # Convert key from snake_case to readable format
        readable_key = key.replace('_', ' ').title()
        parts.append(f"{readable_key}: {value}")
    
    return ", ".join(parts)