from summary_schema import MeetingSummary

def md_from_summary(ms: MeetingSummary) -> str:
    lines = [f"# Community Board Meeting — {ms.meeting_date}",
             f"**Overall sentiment:** {ms.overall_sentiment.title()}",
             "",
             f"**Attendance:** {ms.attendance}"]
    for t in ms.topics:
        lines += ["", f"## {t.title}",
                  f"*Speakers:* {', '.join(t.speakers)}",
                  f"*Sentiment:* {t.sentiment}",
                  "", t.summary,
                  "", "**Decisions:**"]
        lines += [f"- {d}" for d in t.decisions] or ["- _None_"]
        if t.action_items:
            lines += ["", "**Action items:**"]
            for ai in t.action_items:
                lines.append(f"- **{ai.task}** (owner: {ai.owner}, due: {ai.due})")
    return "\n".join(lines)
