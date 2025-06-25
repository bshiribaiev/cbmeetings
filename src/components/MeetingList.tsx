import React, { useState, useEffect } from 'react';
import { Calendar, Clock, FileText, Users, TrendingUp, AlertCircle, ChevronRight, Loader, RefreshCw } from 'lucide-react';

interface MeetingListProps {
  cbNumber: number;
  onSelectMeeting: (meeting: Meeting) => void;
}

interface Meeting {
  video_id: string;
  title: string;
  url: string;
  published_at: string;
  processed_at: string;
  analysis?: {
    summary?: string;
    keyDecisions?: Array<{
      item: string;
      outcome: string;
      vote: string;
      details: string;
    }>;
    mainTopics?: string[];
    attendance?: string;
    summary_markdown?: string;
  };
  transcript_length?: number;
}

interface BoardInfo {
  name: string;
  district: string;
}

const MeetingList: React.FC<MeetingListProps> = ({ cbNumber, onSelectMeeting }) => {
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const boardInfo: Record<number, BoardInfo> = {
    1: { name: 'Manhattan CB1', district: 'Financial District' },
    2: { name: 'Manhattan CB2', district: 'Greenwich Village' },
    3: { name: 'Manhattan CB3', district: 'Lower East Side' },
    4: { name: 'Manhattan CB4', district: 'Chelsea/Clinton' },
    5: { name: 'Manhattan CB5', district: 'Midtown' },
    6: { name: 'Manhattan CB6', district: 'East Midtown' },
    7: { name: 'Manhattan CB7', district: 'Upper West Side' },
    8: { name: 'Manhattan CB8', district: 'Upper East Side' },
    9: { name: 'Manhattan CB9', district: 'West Harlem' },
    10: { name: 'Manhattan CB10', district: 'Central Harlem' },
    11: { name: 'Manhattan CB11', district: 'East Harlem' },
    12: { name: 'Manhattan CB12', district: 'Washington Heights' },
  };

  const currentBoard = boardInfo[cbNumber] || { name: `CB${cbNumber}`, district: 'Manhattan' };

  useEffect(() => {
    fetchMeetings();
  }, [cbNumber]);

  const fetchMeetings = async () => {
    setLoading(true);
    setError(null);
    
    try {
      const response = await fetch(`http://localhost:8000/api/cb/${cbNumber}/meetings`);
      if (!response.ok) throw new Error('Failed to fetch meetings');
      
      const data = await response.json();
      setMeetings(data.meetings || []);
    } catch (err) {
      console.error('Error fetching meetings:', err);
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setLoading(false);
    }
  };

  const refreshVideos = async () => {
    setRefreshing(true);
    try {
      // Fetch new videos from YouTube
      const response = await fetch(`http://localhost:8000/api/cb/cb${cbNumber}/fetch-videos`, {
        method: 'POST'
      });
      
      if (response.ok) {
        const result = await response.json();
        if (result.new_videos > 0) {
          // Refresh the meeting list
          await fetchMeetings();
        }
      }
    } catch (err) {
      console.error('Error refreshing videos:', err);
    } finally {
      setRefreshing(false);
    }
  };

  const formatDate = (dateString: string): string => {
    if (!dateString) return 'Date unknown';
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', { 
      year: 'numeric', 
      month: 'short', 
      day: 'numeric' 
    });
  };

  const getMeetingType = (title: string): { type: string; color: string } => {
    const titleLower = title.toLowerCase();
    if (titleLower.includes('full board')) return { type: 'Full Board', color: '#3182ce' };
    if (titleLower.includes('budget')) return { type: 'Budget', color: '#38a169' };
    if (titleLower.includes('land use')) return { type: 'Land Use', color: '#dd6b20' };
    if (titleLower.includes('parks')) return { type: 'Parks', color: '#38a169' };
    if (titleLower.includes('transportation')) return { type: 'Transportation', color: '#805ad5' };
    if (titleLower.includes('housing')) return { type: 'Housing', color: '#e53e3e' };
    return { type: 'Committee', color: '#718096' };
  };

  if (loading) {
    return (
      <div style={{
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        minHeight: '400px'
      }}>
        <Loader size={32} className="animate-spin" style={{ color: '#3182ce' }} />
      </div>
    );
  }

  if (error) {
    return (
      <div style={{
        textAlign: 'center',
        padding: '3rem',
        color: '#e53e3e'
      }}>
        <AlertCircle size={48} style={{ margin: '0 auto 1rem' }} />
        <p>Error loading meetings: {error}</p>
        <button 
          onClick={fetchMeetings}
          className="btn btn-secondary"
          style={{ marginTop: '1rem' }}
        >
          Try Again
        </button>
      </div>
    );
  }

  const containerStyle = {
    padding: '2rem 1rem',
    maxWidth: '1200px',
    margin: '0 auto'
  };

  const headerStyle = {
    background: 'white',
    borderRadius: '1rem',
    padding: '2rem',
    marginBottom: '2rem',
    boxShadow: '0 1px 3px rgba(0, 0, 0, 0.1)'
  };

  const meetingCardStyle = {
    background: 'white',
    borderRadius: '1rem',
    padding: '1.5rem',
    boxShadow: '0 1px 3px rgba(0, 0, 0, 0.1)',
    cursor: 'pointer',
    transition: 'all 0.2s',
    border: '2px solid transparent'
  };

  return (
    <div className="meeting-list-container" style={containerStyle}>
      {/* Header */}
      <div style={headerStyle}>
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          flexWrap: 'wrap',
          gap: '1rem'
        }}>
          <div>
            <h1 style={{
              fontSize: '2rem',
              fontWeight: '700',
              color: '#1a202c',
              marginBottom: '0.5rem'
            }}>
              {currentBoard.name} Meetings
            </h1>
            <p style={{
              color: '#718096',
              fontSize: '1.125rem'
            }}>
              {currentBoard.district} • {meetings.length} processed meetings
            </p>
          </div>
          
          <button
            onClick={refreshVideos}
            disabled={refreshing}
            className="btn btn-secondary"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem'
            }}
          >
            <RefreshCw size={16} className={refreshing ? 'animate-spin' : ''} />
            {refreshing ? 'Checking...' : 'Check for New Videos'}
          </button>
        </div>
      </div>

      {/* Meeting List */}
      {meetings.length === 0 ? (
        <div style={{
          background: 'white',
          borderRadius: '1rem',
          padding: '3rem',
          textAlign: 'center',
          boxShadow: '0 1px 3px rgba(0, 0, 0, 0.1)'
        }}>
          <FileText size={48} style={{ color: '#a0aec0', margin: '0 auto 1rem' }} />
          <p style={{ color: '#718096', fontSize: '1.125rem' }}>
            No processed meetings found for this board yet.
          </p>
          <button
            onClick={refreshVideos}
            className="btn btn-primary"
            style={{ marginTop: '1rem' }}
          >
            Fetch Videos from YouTube
          </button>
        </div>
      ) : (
        <div style={{
          display: 'grid',
          gap: '1rem'
        }}>
          {meetings.map((meeting) => {
            const meetingType = getMeetingType(meeting.title);
            const analysis = meeting.analysis || {};
            
            return (
              <div
                key={meeting.video_id}
                onClick={() => onSelectMeeting(meeting)}
                style={meetingCardStyle}
                onMouseEnter={(e) => {
                  e.currentTarget.style.transform = 'translateY(-2px)';
                  e.currentTarget.style.boxShadow = '0 4px 12px rgba(0, 0, 0, 0.1)';
                  e.currentTarget.style.borderColor = '#e2e8f0';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.transform = 'translateY(0)';
                  e.currentTarget.style.boxShadow = '0 1px 3px rgba(0, 0, 0, 0.1)';
                  e.currentTarget.style.borderColor = 'transparent';
                }}
              >
                <div style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'flex-start',
                  marginBottom: '1rem'
                }}>
                  <div style={{ flex: 1 }}>
                    <div style={{
                      display: 'inline-block',
                      padding: '0.25rem 0.75rem',
                      borderRadius: '9999px',
                      fontSize: '0.75rem',
                      fontWeight: '600',
                      color: 'white',
                      background: meetingType.color,
                      marginBottom: '0.5rem'
                    }}>
                      {meetingType.type}
                    </div>
                    
                    <h3 style={{
                      fontSize: '1.25rem',
                      fontWeight: '600',
                      color: '#1a202c',
                      marginBottom: '0.5rem',
                      lineHeight: 1.3
                    }}>
                      {meeting.title}
                    </h3>
                    
                    <div style={{
                      display: 'flex',
                      gap: '1.5rem',
                      fontSize: '0.875rem',
                      color: '#718096',
                      flexWrap: 'wrap'
                    }}>
                      <span style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                        <Calendar size={14} />
                        {formatDate(meeting.published_at)}
                      </span>
                      <span style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                        <Clock size={14} />
                        Processed {formatDate(meeting.processed_at)}
                      </span>
                    </div>
                  </div>
                  
                  <ChevronRight size={20} style={{ color: '#a0aec0', flexShrink: 0 }} />
                </div>

                {/* Meeting Stats */}
                {analysis.summary && (
                  <>
                    <p style={{
                      color: '#4a5568',
                      fontSize: '0.95rem',
                      lineHeight: 1.5,
                      marginBottom: '1rem'
                    }}>
                      {analysis.summary.substring(0, 200)}...
                    </p>
                    
                    <div style={{
                      display: 'flex',
                      gap: '2rem',
                      fontSize: '0.875rem',
                      color: '#718096',
                      flexWrap: 'wrap'
                    }}>
                      {analysis.keyDecisions && analysis.keyDecisions.length > 0 && (
                        <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                          <div style={{
                            width: '8px',
                            height: '8px',
                            borderRadius: '50%',
                            background: '#3182ce'
                          }} />
                          {analysis.keyDecisions.length} Decisions
                        </span>
                      )}
                      
                      {analysis.mainTopics && analysis.mainTopics.length > 0 && (
                        <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                          <TrendingUp size={14} />
                          {analysis.mainTopics.length} Topics
                        </span>
                      )}
                      
                      {analysis.attendance && (
                        <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                          <Users size={14} />
                          {analysis.attendance}
                        </span>
                      )}
                    </div>
                  </>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default MeetingList;