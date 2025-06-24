import React from 'react';
import { CheckCircle, TrendingUp, Users, Calendar } from 'lucide-react';

interface MarkdownRendererProps {
  markdown: string;
}

const MarkdownRenderer: React.FC<MarkdownRendererProps> = ({ markdown }) => {
  // Parse the markdown into sections
  const sections = markdown.split(/^## /m).filter(Boolean);
  
  // Extract header info (before first ##)
  const headerMatch = markdown.match(/^(.*?)(?=## )/s);
  const headerContent = headerMatch ? headerMatch[1].trim() : '';
  
  // Parse header content
  const titleMatch = headerContent.match(/# Community Board Meeting — (.+)/);
  const date = titleMatch ? titleMatch[1] : '';
  
  // Extract meeting overview
  const overviewMatch = headerContent.match(/## Meeting Overview\n([\s\S]*?)(?=\*\*Overall Sentiment|$)/);
  const overview = overviewMatch ? overviewMatch[1].trim() : '';
  
  // Extract sentiment and attendance
  const sentimentMatch = headerContent.match(/\*\*Overall Sentiment:\*\* (.+)/);
  const sentiment = sentimentMatch ? sentimentMatch[1] : 'Not specified';
  
  const attendanceMatch = headerContent.match(/\*\*Attendance:\*\* (.+)/);
  const attendance = attendanceMatch ? attendanceMatch[1] : 'Not specified';
  
  // Process each section
  const processSection = (section: string) => {
    const lines = section.trim().split('\n');
    const title = lines[0].replace(/^\d+\.\s*/, '');
    
    const content: any = {
      title,
      speakers: '',
      sentiment: '',
      summary: '',
      decisions: [],
      actionItems: []
    };
    
    let currentSection = '';
    
    for (let i = 1; i < lines.length; i++) {
      const line = lines[i].trim();
      
      if (line.startsWith('**Speakers:**')) {
        content.speakers = line.replace('**Speakers:**', '').trim();
      } else if (line.startsWith('**Sentiment:**')) {
        content.sentiment = line.replace('**Sentiment:**', '').trim();
      } else if (line === '### Summary') {
        currentSection = 'summary';
      } else if (line === '### Decisions') {
        currentSection = 'decisions';
      } else if (line === '### Action Items') {
        currentSection = 'actionItems';
      } else if (line.startsWith('- ')) {
        if (currentSection === 'decisions') {
          content.decisions.push(line.substring(2));
        } else if (currentSection === 'actionItems') {
          // Parse action item
          const actionItem = { task: line.substring(2), owner: '', due: '' };
          // Check next lines for owner and due
          if (i + 1 < lines.length && lines[i + 1].includes('Owner:')) {
            actionItem.owner = lines[i + 1].replace(/.*Owner:\s*/, '').trim();
            i++;
          }
          if (i + 1 < lines.length && lines[i + 1].includes('Due:')) {
            actionItem.due = lines[i + 1].replace(/.*Due:\s*/, '').trim();
            i++;
          }
          content.actionItems.push(actionItem);
        }
      } else if (currentSection === 'summary' && line) {
        content.summary += (content.summary ? ' ' : '') + line;
      }
    }
    
    return content;
  };
  
  const parsedSections = sections.map(processSection);
  
  const getSentimentClass = (sentiment: string) => {
    const sentimentLower = sentiment.toLowerCase();
    if (sentimentLower.includes('positive')) return 'sentiment-positive';
    if (sentimentLower.includes('mixed') || sentimentLower.includes('neutral')) return 'sentiment-mixed';
    if (sentimentLower.includes('negative')) return 'sentiment-negative';
    return 'sentiment-mixed';
  };
  
  return (
    <div style={{ textAlign: 'left' }}>
      {/* Meeting date */}
      {date && (
        <p style={{ color: '#718096', fontSize: '1rem', marginBottom: '2rem' }}>
          <Calendar size={18} style={{ display: 'inline', marginRight: '0.5rem' }} />
          Meeting Date: {date}
        </p>
      )}
      
      {/* Meeting Overview Section */}
      {overview && (
        <>
          <h3 style={{
            fontSize: '1.5rem',
            fontWeight: '600',
            color: '#1a202c',
            marginBottom: '1rem'
          }}>
            Meeting Overview
          </h3>
          <p style={{
            color: '#4a5568',
            fontSize: '1.1rem',
            lineHeight: '1.8',
            marginBottom: '2rem'
          }}>
            {overview}
          </p>
        </>
      )}
      
      {/* Metadata */}
      <div style={{
        display: 'flex',
        gap: '2rem',
        marginBottom: '3rem',
        fontSize: '0.95rem',
        color: '#718096'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <Users size={18} />
          <span>{attendance}</span>
        </div>
        <div className={`badge ${getSentimentClass(sentiment)}`}>
          Overall Sentiment: {sentiment}
        </div>
      </div>
      
      {/* Topic Sections */}
      <h3 style={{
        fontSize: '1.5rem',
        fontWeight: '600',
        color: '#1a202c',
        marginBottom: '2rem'
      }}>
        Meeting Topics & Discussions
      </h3>
      
      {parsedSections.map((section, idx) => (
        <div key={idx} style={{
          background: '#f8fafc',
          borderRadius: '1rem',
          padding: '2rem',
          marginBottom: '2rem',
          border: '1px solid #e2e8f0'
        }}>
          <h4 style={{
            fontSize: '1.25rem',
            fontWeight: '600',
            color: '#2d3748',
            marginBottom: '1rem'
          }}>
            {idx + 1}. {section.title}
          </h4>
          
          {/* Section metadata */}
          <div style={{ marginBottom: '1.5rem' }}>
            {section.speakers && (
              <p style={{ fontSize: '0.9rem', color: '#718096', marginBottom: '0.5rem' }}>
                <strong>Speakers:</strong> {section.speakers}
              </p>
            )}
            {section.sentiment && (
              <span className={`badge ${getSentimentClass(section.sentiment)}`} style={{ fontSize: '0.8rem' }}>
                Topic Sentiment: {section.sentiment}
              </span>
            )}
          </div>
          
          {/* Summary */}
          {section.summary && (
            <>
              <h5 style={{
                fontSize: '1.1rem',
                fontWeight: '600',
                color: '#1a202c',
                marginBottom: '0.75rem'
              }}>
                Summary
              </h5>
              <p style={{
                color: '#4a5568',
                fontSize: '1rem',
                lineHeight: '1.7',
                marginBottom: '1.5rem'
              }}>
                {section.summary}
              </p>
            </>
          )}
          
          {/* Decisions */}
          {section.decisions.length > 0 && (
            <>
              <h5 style={{
                fontSize: '1.1rem',
                fontWeight: '600',
                color: '#1a202c',
                marginBottom: '0.75rem',
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem'
              }}>
                <CheckCircle size={18} />
                Decisions
              </h5>
              <ul style={{ marginBottom: '1.5rem', paddingLeft: '1.5rem' }}>
                {section.decisions.map((decision: string, dIdx: number) => (
                  <li key={dIdx} style={{
                    color: '#4a5568',
                    fontSize: '0.95rem',
                    lineHeight: '1.6',
                    marginBottom: '0.5rem'
                  }}>
                    {decision}
                  </li>
                ))}
              </ul>
            </>
          )}
          
          {/* Action Items */}
          {section.actionItems.length > 0 && (
            <>
              <h5 style={{
                fontSize: '1.1rem',
                fontWeight: '600',
                color: '#1a202c',
                marginBottom: '0.75rem',
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem'
              }}>
                <TrendingUp size={18} />
                Action Items
              </h5>
              <div style={{ paddingLeft: '1.5rem' }}>
                {section.actionItems.map((item: any, aIdx: number) => (
                  <div key={aIdx} style={{ marginBottom: '1rem' }}>
                    <p style={{
                      color: '#2d3748',
                      fontSize: '0.95rem',
                      fontWeight: '600',
                      marginBottom: '0.25rem'
                    }}>
                      {item.task}
                    </p>
                    {(item.owner || item.due) && (
                      <p style={{
                        color: '#718096',
                        fontSize: '0.85rem',
                        paddingLeft: '1rem'
                      }}>
                        {item.owner && <span>Owner: {item.owner}</span>}
                        {item.owner && item.due && <span> • </span>}
                        {item.due && <span>Due: {item.due}</span>}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      ))}
    </div>
  );
};

export default MarkdownRenderer;