from summary_schema import MeetingSummary

def md_from_summary(ms: MeetingSummary) -> str:
    """Convert the rich summary to markdown format"""
    lines = []
    
    # Header
    lines.append(f"# {ms.meeting_type}")
    lines.append(f"**Date:** {ms.meeting_date}")
    lines.append("")
    
    # Executive Summary - This is your rich, detailed summary!
    lines.append("## Meeting Overview")
    lines.append("")
    lines.append(ms.executive_summary)
    lines.append("")
    
    # Meeting stats - more concise
    if ms.total_decisions > 0 or ms.total_action_items > 0:
        lines.append("### Key Statistics")
        stats = []
        if ms.total_decisions > 0:
            stats.append(f"**Decisions Made:** {ms.total_decisions}")
        if ms.total_action_items > 0:
            stats.append(f"**Action Items:** {ms.total_action_items}")
        if ms.overall_sentiment:
            stats.append(f"**Overall Sentiment:** {ms.overall_sentiment.title()}")
        if ms.attendance:
            stats.append(f"**Attendance:** {format_attendance(ms.attendance)}")
        lines.append(" | ".join(stats))
        lines.append("")
    
    # Key Decisions section (if any)
    if ms.key_decisions:
        lines.append("## Key Decisions")
        lines.append("")
        for decision in ms.key_decisions:
            lines.append(f"### {decision.item}")
            if decision.vote:
                lines.append(f"**Vote:** {decision.vote}")
            lines.append(f"**Outcome:** {decision.outcome}")
            if decision.details:
                lines.append(f"")
                lines.append(decision.details)
            lines.append("")
    
    # Detailed topic sections
    if ms.topics:
        lines.append("## Detailed Discussion Topics")
        lines.append("")
        
        for i, topic in enumerate(ms.topics, 1):
            lines.append(f"### {i}. {topic.title}")
            lines.append("")
            
            # Topic metadata
            if topic.speakers:
                lines.append(f"**Speakers:** {', '.join(topic.speakers)}")
                lines.append("")
            
            # Topic summary - the detailed one
            lines.append(topic.summary)
            lines.append("")
            
            # Key points if available
            if hasattr(topic, 'key_points') and topic.key_points:
                lines.append("**Key Points:**")
                for point in topic.key_points:
                    lines.append(f"- {point}")
                lines.append("")
            
            # Decisions with details
            if topic.decisions:
                lines.append("**Decisions:**")
                for decision in topic.decisions:
                    lines.append(f"- {decision}")
                lines.append("")
            
            # Concerns raised
            if hasattr(topic, 'concerns_raised') and topic.concerns_raised:
                lines.append("**Concerns Raised:**")
                for concern in topic.concerns_raised:
                    lines.append(f"- {concern}")
                lines.append("")
            
            # Action items with full details
            if topic.action_items:
                lines.append("**Action Items:**")
                for ai in topic.action_items:
                    lines.append(f"- {ai.task}")
                    lines.append(f"  - Owner: {ai.owner}")
                    lines.append(f"  - Due: {ai.due}")
                lines.append("")
    
    # Public Concerns section
    if ms.public_concerns:
        lines.append("## Public Concerns")
        lines.append("")
        for concern in ms.public_concerns:
            lines.append(f"- {concern}")
        lines.append("")
    
    # Next Steps section
    if ms.next_steps:
        lines.append("## Next Steps")
        lines.append("")
        for step in ms.next_steps:
            lines.append(f"- {step}")
        lines.append("")
    
    return "\n".join(lines)

def format_attendance(attendance: dict) -> str:
    if not attendance:
        return "Not specified"
    
    parts = []
    for key, value in attendance.items():
        readable_key = key.replace('_', ' ').title()
        parts.append(f"{readable_key}: {value}")
        
    return ", ".join(parts)