import React, { useState, useEffect } from 'react';
import { Calendar, Clock, FileText, Users, TrendingUp, AlertCircle, ChevronRight, Loader, RefreshCw, X } from 'lucide-react';

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
  status?: string;
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
    publicConcerns?: string[];
    nextSteps?: string[];
    sentiment?: string;
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
  const [searchTerm, setSearchTerm] = useState('');
  const [lastFetch, setLastFetch] = useState<Date | null>(null);

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
    // Initial fetch
    fetchMeetings();
  }, [cbNumber]);
  
  useEffect(() => {
    // Auto-refresh every 30 seconds, but only if not loading
    const interval = setInterval(() => {
      if (!loading) {
        fetchMeetings(true); // true = auto-refresh
      }
    }, 30000);
    
    return () => clearInterval(interval);
  }, [cbNumber, loading]);

  const fetchMeetings = async (isAutoRefresh = false) => {
    console.log(`[fetchMeetings] Starting fetch for CB${cbNumber}, autoRefresh=${isAutoRefresh}`);
    
    // Don't set loading state for auto-refresh
    if (!isAutoRefresh) {
      setLoading(true);
    }
    setError(null);
    
    const fetchStart = Date.now();
    
    try {
      const url = `https://cbmeetings.onrender.com/api/cb/${cbNumber}/meetings`;
      console.log(`[fetchMeetings] Fetching from: ${url}`);
      
      const response = await fetch(url);
      const fetchTime = Date.now() - fetchStart;
      console.log(`[fetchMeetings] Response received in ${fetchTime}ms, status: ${response.status}`);
      
      if (!response.ok) {
        const errorText = await response.text();
        console.error('[fetchMeetings] Error response:', errorText);
        throw new Error(`Failed to fetch meetings: ${response.status}`);
      }
      
      const parseStart = Date.now();
      const data = await response.json();
      const parseTime = Date.now() - parseStart;
      
      console.log(`[fetchMeetings] JSON parsed in ${parseTime}ms`);
      console.log(`[fetchMeetings] Received data:`, {
        meetings_count: data.meetings?.length || 0,
        total: data.total,
        has_error: !!data.error
      });
      
      // Check if there's a database lock error
      if (data.error && data.error.includes('temporarily unavailable')) {
        // Show cached meetings if available, or previous state
        if (meetings.length > 0 && isAutoRefresh) {
          // Keep existing meetings during auto-refresh if DB is locked
          console.log('Database locked, keeping existing meetings');
          return;
        }
      }
      
      setMeetings(data.meetings || []);
      setLastFetch(new Date());
      
      const totalTime = Date.now() - fetchStart;
      console.log(`[fetchMeetings] Total operation time: ${totalTime}ms`);
      
    } catch (err) {
      const totalTime = Date.now() - fetchStart;
      console.error(`[fetchMeetings] Error after ${totalTime}ms:`, err);
      
      // For auto-refresh, don't show error - just keep existing data
      if (isAutoRefresh && meetings.length > 0) {
        console.log('[fetchMeetings] Auto-refresh failed, keeping existing meetings');
        return;
      }
      
      setError(err instanceof Error ? err.message : 'An error occurred');
      // Don't completely fail - show existing meetings if available
      if (meetings.length === 0) {
        setMeetings([]);
      }
    } finally {
      if (!isAutoRefresh) {
        setLoading(false);
      }
    }
  };

  const refreshVideos = async () => {
    setRefreshing(true);
    try {
      // Fetch new videos from YouTube
      const response = await fetch(`https://cbmeetings.onrender.com/api/cb/cb${cbNumber}/fetch-videos`, {
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

  // Function to extract meeting overview from markdown
  const extractOverviewFromMarkdown = (markdown: string): string => {
    if (!markdown) return '';
    
    // Find the Meeting Overview section
    const overviewMatch = markdown.match(/## Meeting Overview\s*\n\s*([^#]+)/);
    if (overviewMatch) {
      // Clean up the extracted text
      return overviewMatch[1].trim().replace(/\*\*/g, '').replace(/\n/g, ' ');
    }
    return '';
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

  // Filter meetings based on search term
  const filteredMeetings = meetings.filter(meeting => {
    if (!searchTerm) return true;
    
    const searchLower = searchTerm.toLowerCase();
    
    // Search in title
    if (meeting.title.toLowerCase().includes(searchLower)) return true;
    
    // Search in the FULL markdown content, not just the overview
    if (meeting.analysis?.summary_markdown) {
      if (meeting.analysis.summary_markdown.toLowerCase().includes(searchLower)) return true;
    }
    
    // Search in regular summary
    if (meeting.analysis?.summary && meeting.analysis.summary.toLowerCase().includes(searchLower)) return true;
    
    // Search in main topics
    if (meeting.analysis?.mainTopics) {
      if (meeting.analysis.mainTopics.some(topic => 
        topic.toLowerCase().includes(searchLower)
      )) return true;
    }
    
    // Search in key decisions
    if (meeting.analysis?.keyDecisions) {
      for (const decision of meeting.analysis.keyDecisions) {
        if (decision.item?.toLowerCase().includes(searchLower) ||
            decision.outcome?.toLowerCase().includes(searchLower) ||
            decision.details?.toLowerCase().includes(searchLower)) {
          return true;
        }
      }
    }
    
    // Search in public concerns
    if (meeting.analysis?.publicConcerns) {
      if (meeting.analysis.publicConcerns.some((concern: string) => 
        concern.toLowerCase().includes(searchLower)
      )) return true;
    }
    
    return false;
  });

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
          onClick={() => fetchMeetings()}
          className="btn btn-secondary"
          style={{ marginTop: '1rem' }}
        >
          Try Again
        </button>
      </div>
    );
  }

  const containerStyle = {
    maxWidth: '720px',
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
    border: '2px solid transparent',
    maxHeight: '400px',
    overflow: 'hidden',
    position: 'relative' as const
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
              {currentBoard.district} • {meetings.length} total meetings{filteredMeetings.length < meetings.length && ` • ${filteredMeetings.length} matching search`}
              {lastFetch && (
                <span style={{ fontSize: '0.875rem', marginLeft: '1rem' }}>
                  • Updated {new Date().getTime() - lastFetch.getTime() < 60000 
                    ? 'just now' 
                    : `${Math.floor((new Date().getTime() - lastFetch.getTime()) / 60000)} min ago`}
                </span>
              )}
            </p>
          </div>
          
          <button
            onClick={() => refreshVideos()}
            disabled={refreshing}
            className="btn btn-secondary"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              marginBottom: '10px'
            }}
          >
            <RefreshCw size={16} className={refreshing ? 'animate-spin' : ''} />
            {refreshing ? 'Checking...' : 'Check for New Videos'}
          </button>
        </div>
        
        {/* Search Bar */}
        <div style={{
          background: 'white',
          borderRadius: '1rem',
          padding: '1rem',
          marginBottom: '1.5rem',
          boxShadow: '0 1px 3px rgba(0, 0, 0, 0.1)',
          display: 'flex',
          alignItems: 'center',
          gap: '0.75rem'
        }}>
          <svg 
            width="20" 
            height="20" 
            viewBox="0 0 24 24" 
            fill="none" 
            stroke="#718096" 
            strokeWidth="2" 
            strokeLinecap="round" 
            strokeLinejoin="round"
          >
            <circle cx="11" cy="11" r="8"></circle>
            <path d="m21 21-4.35-4.35"></path>
          </svg>
          
          <input
            type="text"
            placeholder="Search in titles, summaries, decisions, speakers, topics..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            style={{
              flex: 1,
              border: 'none',
              outline: 'none',
              fontSize: '1rem',
              color: '#2d3748',
              background: 'transparent'
            }}
          />
          
          {searchTerm && (
            <button
              onClick={() => setSearchTerm('')}
              style={{
                background: '#f7fafc',
                border: 'none',
                borderRadius: '0.5rem',
                padding: '0.5rem',
                cursor: 'pointer',
                color: '#718096',
                transition: 'all 0.2s'
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = '#e2e8f0';
                e.currentTarget.style.color = '#4a5568';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = '#f7fafc';
                e.currentTarget.style.color = '#718096';
              }}
            >
              <X size={16} />
            </button>
          )}
        </div>
      </div>

      {/* Meeting List */}
      {filteredMeetings.length === 0 ? (
        <div style={{
          background: 'white',
          borderRadius: '1rem',
          padding: '3rem',
          textAlign: 'center',
          boxShadow: '0 1px 3px rgba(0, 0, 0, 0.1)'
        }}>
          <FileText size={48} style={{ color: '#a0aec0', margin: '0 auto 1rem' }} />
          <p style={{ color: '#718096', fontSize: '1.125rem' }}>
            {searchTerm 
              ? `No meetings found matching "${searchTerm}"`
              : 'No processed meetings found for this board yet.'
            }
          </p>
          {!searchTerm && (
            <button
              onClick={() => refreshVideos()}
              className="btn btn-primary"
              style={{ marginTop: '1rem' }}
            >
              Fetch Videos from YouTube
            </button>
          )}
        </div>
      ) : (
        <div style={{
          display: 'grid',
          gap: '1rem'
        }}>
          {filteredMeetings.map((meeting) => {
            const meetingType = getMeetingType(meeting.title);
            const analysis = meeting.analysis || {};
            
            return (
              <div
                key={meeting.video_id}
                onClick={() => {
                  if ((meeting.status === 'completed' || meeting.status === 'processing') && meeting.analysis) {
                    onSelectMeeting(meeting);
                  } else if (meeting.status === 'pending') {
                    // Open YouTube URL for manual processing
                    window.open(meeting.url, '_blank');
                  }
                }}
                style={{
                  ...meetingCardStyle,
                  opacity: meeting.status === 'processing' ? 0.8 : 1
                }}
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
                    <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.5rem' }}>
                      <div style={{
                        display: 'inline-block',
                        padding: '0.25rem 0.75rem',
                        borderRadius: '9999px',
                        fontSize: '0.75rem',
                        fontWeight: '600',
                        color: 'white',
                        background: meetingType.color,
                      }}>
                        {meetingType.type}
                      </div>
                      
                      {meeting.status === 'pending' && (
                        <div style={{
                          display: 'inline-block',
                          padding: '0.25rem 0.75rem',
                          borderRadius: '9999px',
                          fontSize: '0.75rem',
                          fontWeight: '600',
                          color: '#744210',
                          background: '#fef3c7',
                          border: '1px solid #f59e0b'
                        }}>
                          Not Processed
                        </div>
                      )}
                      
                      {meeting.status === 'processing' && (
                        <div style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '0.5rem',
                          padding: '0.25rem 0.75rem',
                          borderRadius: '9999px',
                          fontSize: '0.75rem',
                          fontWeight: '600',
                          color: '#1e40af',
                          background: '#dbeafe',
                          border: '1px solid #3b82f6'
                        }}>
                          <Loader size={12} className="animate-spin" />
                          Processing
                        </div>
                      )}
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
                        {meeting.status === 'completed' 
                          ? `Processed ${formatDate(meeting.processed_at)}`
                          : 'Ready to process'
                        }
                      </span>
                    </div>
                  </div>
                  
                  <ChevronRight size={20} style={{ color: '#a0aec0', flexShrink: 0 }} />
                </div>

                {/* Meeting Stats */}
                {(analysis.summary_markdown || analysis.summary) && (
                  <>
                    <p style={{
                      color: '#4a5568',
                      fontSize: '0.95rem',
                      lineHeight: 1.6,
                      marginBottom: '1rem',
                      display: '-webkit-box',
                      WebkitLineClamp: 4,
                      WebkitBoxOrient: 'vertical',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis'
                    }}>
                      {analysis.summary_markdown 
                        ? extractOverviewFromMarkdown(analysis.summary_markdown)
                        : analysis.summary}
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
                
                {/* Show message for pending videos */}
                {meeting.status === 'pending' && (
                  <div style={{
                    color: '#92400e',
                    fontSize: '0.875rem',
                    background: '#fef3c7',
                    padding: '0.75rem',
                    borderRadius: '0.5rem',
                    marginTop: '0.5rem',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.5rem'
                  }}>
                    <AlertCircle size={16} />
                    Click to open in YouTube, then copy the URL to the analyzer to process
                  </div>
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