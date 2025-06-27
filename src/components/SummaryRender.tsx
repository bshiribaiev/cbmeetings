import React from 'react';
import {
  FileText,
  Calendar,
  Users,
  TrendingUp,
  CheckSquare,
  MessageSquare,
  List,
  AlertTriangle,
  ClipboardList,
  Tag
} from 'lucide-react';

// Helper to format date string
const formatDate = (dateString: string) => {
  try {
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    });
  } catch (e) {
    return dateString; // Fallback to original string if invalid
  }
};

// Main component
const SummaryRender = ({ summaryData, title, cbNumber }: { summaryData: any, title: string, cbNumber?: number }) => {
  if (!summaryData) {
    return <div>Loading summary...</div>;
  }

  const {
    meeting_type,
    meeting_date,
    executive_summary,
    key_decisions = [],
    public_concerns = [],
    next_steps = [],
    topics = [],
    attendance,
    overall_sentiment
  } = summaryData;

  const renderAttendance = (att: any) => {
    if (!att) return 'Not specified';
    return Object.entries(att)
      .map(([key, value]) => `${key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}: ${value}`)
      .join(', ');
  };

  return (
    <div className="summary-container">
      {/* Header Card */}
      <div className="summary-header">
        <div className="summary-header-tag">{meeting_type || 'Meeting'}</div>
        <h1 className="summary-header-title">
          {`CB${cbNumber || ''} ${title}`}
        </h1>
        <div className="summary-header-meta">
          <div className="meta-item">
            <Calendar size={16} />
            <span>{formatDate(meeting_date)}</span>
          </div>
          <div className="meta-item">
            <Users size={16} />
            <span>{renderAttendance(attendance)}</span>
          </div>
          <div className="meta-item">
            <TrendingUp size={16} />
            <span>{overall_sentiment}</span>
          </div>
        </div>
      </div>

      {/* Main Content Sections */}
      <div className="summary-section">
        <h2 className="summary-section-title">
          <FileText size={20} />
          Meeting Overview
        </h2>
        <p className="summary-section-content">
          {executive_summary}
        </p>
      </div>

      {key_decisions.length > 0 && (
        <div className="summary-section">
          <h2 className="summary-section-title">
            <CheckSquare size={20} />
            Key Decisions
          </h2>
          <div className="decisions-grid">
            {key_decisions.map((decision: any, index: number) => (
              <div key={index} className="decision-card">
                <p className="decision-card-item">{decision.item}</p>
                <div className="decision-card-details">
                  <span>{decision.outcome}</span>
                  {decision.vote && <span className="decision-card-vote">{decision.vote}</span>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {topics.length > 0 && (
        <div className="summary-section">
          <h2 className="summary-section-title">
            <MessageSquare size={20} />
            Discussion Topics
          </h2>
          {topics.map((topic: any, index: number) => (
            <div key={index} className="topic-item">
              <h3 className="topic-title">{topic.title}</h3>
              <p className="topic-summary">{topic.summary}</p>
              {topic.speakers && topic.speakers.length > 0 && (
                 <div className="topic-meta">
                    <Tag size={14} />
                    <span>Speakers: {topic.speakers.join(', ')}</span>
                 </div>
              )}
            </div>
          ))}
        </div>
      )}

      {public_concerns.length > 0 && (
        <div className="summary-section">
          <h2 className="summary-section-title concern">
            <AlertTriangle size={20} />
            Public Concerns
          </h2>
          <ul className="summary-list">
            {public_concerns.map((concern: string, index: number) => (
              <li key={index}>{concern}</li>
            ))}
          </ul>
        </div>
      )}
      
      {next_steps.length > 0 && (
        <div className="summary-section">
          <h2 className="summary-section-title">
            <ClipboardList size={20} />
            Next Steps & Action Items
          </h2>
          <ul className="summary-list">
            {next_steps.map((step: string, index: number) => (
              <li key={index}>{step}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};

export default SummaryRender;
