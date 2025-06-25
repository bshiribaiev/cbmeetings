import React from 'react';
import { CheckCircle, TrendingUp, Users, Calendar } from 'lucide-react';

interface MarkdownRendererProps {
  markdown: string;
}

const MarkdownRenderer: React.FC<MarkdownRendererProps> = ({ markdown }) => {
  // Parse the markdown more carefully
  const lines = markdown.split('\n');
  let date = '';
  let overviewText = '';
  let sentiment = 'Not specified';
  let attendance = 'Not specified';
  const sections: any[] = [];
  
  let currentSection: any = null;
  let currentSubsection = '';
  let inOverview = false;
  let sectionCounter = 0;
  
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    
    // Extract date from header
    if (line.startsWith('# Community Board Meeting —')) {
      date = line.replace('# Community Board Meeting —', '').trim();
      continue;
    }
    
    // Check if we're in the Meeting Overview section
    if (line === '## Meeting Overview') {
      inOverview = true;
      continue;
    }
    
    // Extract overview text
    if (inOverview && line && !line.startsWith('**')) {
      overviewText = line;
      inOverview = false;
      continue;
    }
    
    // Extract sentiment and attendance
    if (line.startsWith('**Overall Sentiment:**')) {
      sentiment = line.replace('**Overall Sentiment:**', '').trim();
      continue;
    }
    
    if (line.startsWith('**Attendance:**')) {
      attendance = line.replace('**Attendance:**', '').trim();
      continue;
    }
    
    // Parse numbered sections (topics)
    if (line.match(/^## \d+\./)) {
      // Save previous section if exists
      if (currentSection) {
        sections.push(currentSection);
      }
      
      sectionCounter++;
      const title = line.replace(/^## \d+\./, '').trim();
      currentSection = {
        number: sectionCounter,
        title,
        speakers: '',
        sentiment: '',
        summary: '',
        decisions: [],
        actionItems: []
      };
      currentSubsection = '';
      continue;
    }
    
    // Parse section content
    if (currentSection) {
      if (line.startsWith('**Speakers:**')) {
        currentSection.speakers = line.replace('**Speakers:**', '').trim();
      } else if (line.startsWith('**Sentiment:**')) {
        currentSection.sentiment = line.replace('**Sentiment:**', '').trim();
      } else if (line === '### Summary') {
        currentSubsection = 'summary';
      } else if (line === '### Decisions') {
        currentSubsection = 'decisions';
      } else if (line === '### Action Items') {
        currentSubsection = 'actionItems';
      } else if (line.startsWith('- ')) {
        if (currentSubsection === 'decisions') {
          currentSection.decisions.push(line.substring(2));
        } else if (currentSubsection === 'actionItems') {
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
          currentSection.actionItems.push(actionItem);
        }
      } else if (currentSubsection === 'summary' && line) {
        currentSection.summary += (currentSection.summary ? ' ' : '') + line;
      }
    }
  }
  
  // Don't forget the last section
  if (currentSection) {
    sections.push(currentSection);
  }
  
  const getSentimentClass = (sentiment: string) => {
    const sentimentLower = sentiment.toLowerCase();
    if (sentimentLower.includes('positive')) return 'sentiment-positive';
    if (sentimentLower.includes('mixed') || sentimentLower.includes('neutral')) return 'sentiment-mixed';
    if (sentimentLower.includes('negative')) return 'sentiment-negative';
    return 'sentiment-mixed';
  };
  
  return (
    <div style={{ textAlign: 'left' }}>
      {/* Meeting Overview Section */}
      {overviewText && (
        <>
          <h3 style={{
            fontSize: '1.5rem',
            fontWeight: '600',
            color: '#1a202c',
            marginTop: '1rem',
            marginBottom: '1rem' 
          }}>
            Meeting Overview
          </h3>

          <p style={{
            color: 'black',
            fontSize: '1.1rem',
            lineHeight: '1.8',
            marginBottom: '2rem'
          }}>
            {overviewText}
          </p>
        </>
      )}
      
      {/* Metadata */}
      <div style={{
        display: 'flex',
        gap: '2rem',
        marginBottom: '3rem',
        fontSize: '0.95rem',
        color: '#718096',
        flexWrap: 'wrap'
      }}>
        {date && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Calendar size={18} />
            <span>Meeting Date: {date}</span>
          </div>
        )}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <span>Attendees: {attendance}</span>
        </div>
        <div className={`badge ${getSentimentClass(sentiment)}`}>
          Overall Sentiment: {sentiment}
        </div>
      </div>
      
      {/* Summary section would go here if needed */}
      
      {/* Topic Sections */}
      {sections.length > 0 && (
        <>
          <h3 style={{
            fontSize: '1.5rem',
            fontWeight: '600',
            color: '#1a202c',
            marginBottom: '2rem'
          }}>
            Meeting Topics & Discussions
          </h3>
          
          {sections.map((section, idx) => (
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
                {section.number}. {section.title}
              </h4>
              
              {/* Section metadata */}
              <div style={{ marginBottom: '1.5rem' }}>
                {section.speakers && (
                  <p style={{ fontSize: '0.9rem', color: '#718096', marginBottom: '0.5rem' }}>
                    <strong>Speakers:</strong> {section.speakers}
                  </p>
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
                    Decisions
                  </h5>
                  <ul style={{ marginBottom: '1.5rem' }}>
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
                    Action Items
                  </h5>
                  <div >
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
              {section.sentiment && (
                  <span className={`badge ${getSentimentClass(section.sentiment)}`} style={{ fontSize: '0.8rem' }}>
                    Topic Sentiment: {section.sentiment}
                  </span>
                )}
            </div>
          ))}
        </>
      )}
    </div>
  );
};

export default MarkdownRenderer;