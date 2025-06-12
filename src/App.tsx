import { useState, useEffect } from 'react';
import { Calendar, Clock, CheckCircle, AlertCircle, Loader, Eye, Download, Bell, Settings, Activity } from 'lucide-react';

interface ProcessedMeeting {
  video_id: string;
  title: string;
  published_at: string;
  processed_at: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  analysis?: {
    summary: string;
    keyDecisions: Array<{
      item: string;
      outcome: string;
      vote: string;
      details: string;
    }>;
    publicConcerns: string[];
    nextSteps: string[];
    sentiment: string;
    attendance: string;
    mainTopics: string[];
  };
}

interface SystemStatus {
  isRunning: boolean;
  lastCheck: string;
  totalProcessed: number;
  pendingVideos: number;
  lastError?: string;
}

const AutonomousCB7Dashboard = () => {
  const [meetings, setMeetings] = useState<ProcessedMeeting[]>([]);
  const [systemStatus, setSystemStatus] = useState<SystemStatus>({
    isRunning: true,
    lastCheck: '2024-01-15 14:30:00',
    totalProcessed: 12,
    pendingVideos: 2
  });
  const [selectedMeeting, setSelectedMeeting] = useState<ProcessedMeeting | null>(null);
  const [loading, setLoading] = useState(false);

  // Mock data for demonstration
  const mockMeetings: ProcessedMeeting[] = [
    {
      video_id: 'abc123',
      title: 'CB7 Full Board Meeting - January 2024',
      published_at: '2024-01-10T19:00:00Z',
      processed_at: '2024-01-10T22:45:00Z',
      status: 'completed',
      analysis: {
        summary: 'Community Board 7 discussed zoning changes on West 79th Street and approved new bike lane pilot program. Significant community input on affordable housing initiatives.',
        keyDecisions: [
          {
            item: 'West 79th Street Bike Lane Pilot',
            outcome: 'Approved',
            vote: '11-4',
            details: '6-month pilot program with monthly community feedback sessions'
          },
          {
            item: 'Zoning Application - 2350 Broadway',
            outcome: 'Approved with Conditions',
            vote: '9-6',
            details: 'Approved with height reduction and affordable housing requirement'
          }
        ],
        publicConcerns: [
          'Construction noise affecting elderly residents',
          'Need for more accessible playground equipment',
          'Traffic congestion during school hours'
        ],
        nextSteps: [
          'Schedule bike lane implementation meeting',
          'Form affordable housing working group',
          'Coordinate with DOT on traffic study'
        ],
        sentiment: 'Cautiously Optimistic',
        attendance: '14 board members, ~75 community members',
        mainTopics: ['Transportation', 'Zoning', 'Housing', 'Parks']
      }
    },
    {
      video_id: 'def456',
      title: 'CB7 Transportation Committee - January 2024',
      published_at: '2024-01-08T18:30:00Z',
      processed_at: '2024-01-08T19:15:00Z',
      status: 'completed',
      analysis: {
        summary: 'Transportation Committee reviewed bike lane proposals and discussed traffic safety improvements around local schools.',
        keyDecisions: [
          {
            item: 'School Zone Speed Cameras',
            outcome: 'Supported',
            vote: 'Unanimous',
            details: 'Full committee support for DOT proposal'
          }
        ],
        publicConcerns: [
          'Speeding vehicles near PS 163',
          'Inadequate crosswalk signals on Amsterdam Ave'
        ],
        nextSteps: [
          'Submit formal letter to DOT',
          'Request meeting with school principals'
        ],
        sentiment: 'Positive',
        attendance: '8 committee members, ~20 community members',
        mainTopics: ['Traffic Safety', 'School Zones', 'Bike Infrastructure']
      }
    },
    {
      video_id: 'ghi789',
      title: 'CB7 Land Use Committee - December 2023',
      published_at: '2023-12-15T19:00:00Z',
      processed_at: '2023-12-15T21:30:00Z',
      status: 'completed',
      analysis: {
        summary: 'Land Use Committee reviewed several development applications and discussed affordable housing requirements.',
        keyDecisions: [
          {
            item: 'Luxury Development - West End Avenue',
            outcome: 'Rejected',
            vote: '2-6',
            details: 'Insufficient affordable housing component'
          }
        ],
        publicConcerns: [
          'Gentrification displacing longtime residents',
          'Lack of affordable housing options'
        ],
        nextSteps: [
          'Request revised proposal with more affordable units',
          'Schedule community forum on housing'
        ],
        sentiment: 'Mixed',
        attendance: '8 committee members, ~45 community members',
        mainTopics: ['Development', 'Affordable Housing', 'Zoning']
      }
    },
    {
      video_id: 'jkl012',
      title: 'CB7 Parks Committee - December 2023',
      published_at: '2023-12-12T18:00:00Z',
      processed_at: '2023-12-12T18:45:00Z',
      status: 'processing'
    },
    {
      video_id: 'mno345',
      title: 'CB7 Special Meeting - Budget Discussion',
      published_at: '2023-12-10T17:00:00Z',
      processed_at: '2023-12-10T17:30:00Z',
      status: 'failed'
    }
  ];

  useEffect(() => {
    // Simulate loading meetings
    setLoading(true);
    setTimeout(() => {
      setMeetings(mockMeetings);
      setLoading(false);
    }, 1000);

    // Update system status every 30 seconds
    const interval = setInterval(() => {
      setSystemStatus(prev => ({
        ...prev,
        lastCheck: new Date().toISOString().slice(0, 19).replace('T', ' ')
      }));
    }, 30000);

    return () => clearInterval(interval);
  }, []);

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return <CheckCircle className="w-5 h-5 text-green-500" />;
      case 'processing':
        return <Loader className="w-5 h-5 text-blue-500 animate-spin" />;
      case 'failed':
        return <AlertCircle className="w-5 h-5 text-red-500" />;
      default:
        return <Clock className="w-5 h-5 text-gray-400" />;
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed': return 'bg-green-100 text-green-800';
      case 'processing': return 'bg-blue-100 text-blue-800';
      case 'failed': return 'bg-red-100 text-red-800';
      default: return 'bg-gray-100 text-gray-800';
    }
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const getSentimentColor = (sentiment: string) => {
    switch (sentiment) {
      case 'Positive': return 'text-green-600 bg-green-50';
      case 'Cautiously Optimistic': return 'text-yellow-600 bg-yellow-50';
      case 'Mixed': return 'text-orange-600 bg-orange-50';
      case 'Negative': return 'text-red-600 bg-red-50';
      default: return 'text-gray-600 bg-gray-50';
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-green-50">
      <div className="max-w-7xl mx-auto px-4 py-8">
        {/* Header */}
        <div className="bg-white rounded-2xl shadow-xl p-6 mb-8">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h1 className="text-3xl font-bold text-gray-900 flex items-center">
                <Activity className="w-8 h-8 mr-3 text-blue-600" />
                Autonomous CB7 Monitor
              </h1>
              <p className="text-gray-600 mt-1">Automatically processing Community Board 7 meetings</p>
            </div>
            <div className="flex items-center gap-3">
              <div className={`flex items-center px-3 py-2 rounded-lg ${
                systemStatus.isRunning ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
              }`}>
                <div className={`w-2 h-2 rounded-full mr-2 ${
                  systemStatus.isRunning ? 'bg-green-500' : 'bg-red-500'
                }`}></div>
                {systemStatus.isRunning ? 'Running' : 'Stopped'}
              </div>
              <button className="p-2 text-gray-600 hover:text-gray-900 rounded-lg hover:bg-gray-100">
                <Settings className="w-5 h-5" />
              </button>
            </div>
          </div>

          {/* System Stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-blue-50 rounded-lg p-4 text-center">
              <div className="text-2xl font-bold text-blue-600">{systemStatus.totalProcessed}</div>
              <div className="text-sm text-blue-700">Total Processed</div>
            </div>
            <div className="bg-green-50 rounded-lg p-4 text-center">
              <div className="text-2xl font-bold text-green-600">
                {meetings.filter(m => m.status === 'completed').length}
              </div>
              <div className="text-sm text-green-700">Completed</div>
            </div>
            <div className="bg-yellow-50 rounded-lg p-4 text-center">
              <div className="text-2xl font-bold text-yellow-600">{systemStatus.pendingVideos}</div>
              <div className="text-sm text-yellow-700">Pending</div>
            </div>
            <div className="bg-purple-50 rounded-lg p-4 text-center">
              <div className="text-sm text-purple-700">Last Check</div>
              <div className="text-sm font-medium text-purple-600">{systemStatus.lastCheck}</div>
            </div>
          </div>
        </div>

        {/* Meetings List */}
        <div className="bg-white rounded-2xl shadow-xl p-6">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-xl font-bold text-gray-900">Recent Meetings</h2>
            <div className="flex gap-2">
              <button className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 flex items-center">
                <Download className="w-4 h-4 mr-2" />
                Export All
              </button>
            </div>
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader className="w-8 h-8 text-blue-500 animate-spin" />
              <span className="ml-3 text-gray-600">Loading meetings...</span>
            </div>
          ) : (
            <div className="space-y-4">
              {meetings.map((meeting) => (
                <div
                  key={meeting.video_id}
                  className="border border-gray-200 rounded-lg p-4 hover:shadow-md transition-shadow cursor-pointer"
                  onClick={() => setSelectedMeeting(meeting)}
                >
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="font-medium text-gray-900 flex-1">{meeting.title}</h3>
                    <div className="flex items-center gap-3">
                      <span className={`px-2 py-1 rounded text-xs font-medium ${getStatusColor(meeting.status)}`}>
                        {meeting.status}
                      </span>
                      {getStatusIcon(meeting.status)}
                    </div>
                  </div>

                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm text-gray-600">
                    <div className="flex items-center">
                      <Calendar className="w-4 h-4 mr-1" />
                      {formatDate(meeting.published_at)}
                    </div>
                    <div className="flex items-center">
                      <Clock className="w-4 h-4 mr-1" />
                      {formatDate(meeting.processed_at)}
                    </div>
                    {meeting.analysis && (
                      <>
                        <div className={`px-2 py-1 rounded text-xs ${getSentimentColor(meeting.analysis.sentiment)}`}>
                          {meeting.analysis.sentiment}
                        </div>
                        <div className="text-xs">
                          {meeting.analysis.keyDecisions.length} decisions, {meeting.analysis.publicConcerns.length} concerns
                        </div>
                      </>
                    )}
                  </div>

                  {meeting.analysis && (
                    <div className="mt-3 pt-3 border-t border-gray-100">
                      <p className="text-sm text-gray-700 line-clamp-2">{meeting.analysis.summary}</p>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Meeting Detail Modal */}
        {selectedMeeting && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
            <div className="bg-white rounded-2xl max-w-4xl w-full max-h-[90vh] overflow-y-auto">
              <div className="p-6">
                <div className="flex justify-between items-start mb-6">
                  <div>
                    <h2 className="text-2xl font-bold text-gray-900 mb-2">{selectedMeeting.title}</h2>
                    <div className="flex items-center gap-4 text-sm text-gray-600">
                      <span>Published: {formatDate(selectedMeeting.published_at)}</span>
                      <span>Processed: {formatDate(selectedMeeting.processed_at)}</span>
                    </div>
                  </div>
                  <button
                    onClick={() => setSelectedMeeting(null)}
                    className="text-gray-400 hover:text-gray-600 text-2xl font-light"
                  >
                    ×
                  </button>
                </div>

                {selectedMeeting.analysis ? (
                  <div className="space-y-6">
                    {/* Summary */}
                    <div className="bg-blue-50 rounded-lg p-4">
                      <h3 className="font-semibold text-blue-900 mb-2">Meeting Summary</h3>
                      <p className="text-blue-800">{selectedMeeting.analysis.summary}</p>
                      <div className="mt-2 flex items-center gap-4 text-sm">
                        <span className={`px-2 py-1 rounded ${getSentimentColor(selectedMeeting.analysis.sentiment)}`}>
                          {selectedMeeting.analysis.sentiment}
                        </span>
                        <span className="text-blue-700">{selectedMeeting.analysis.attendance}</span>
                      </div>
                    </div>

                    {/* Key Decisions */}
                    <div>
                      <h3 className="font-semibold text-gray-900 mb-3">Key Decisions</h3>
                      <div className="space-y-3">
                        {selectedMeeting.analysis.keyDecisions.map((decision, idx) => (
                          <div key={idx} className="border border-gray-200 rounded-lg p-3">
                            <div className="flex items-center justify-between mb-1">
                              <h4 className="font-medium text-gray-900">{decision.item}</h4>
                              <div className="flex items-center gap-2">
                                <span className={`px-2 py-1 rounded text-xs font-medium ${
                                  decision.outcome.includes('Approved') 
                                    ? 'bg-green-100 text-green-800'
                                    : 'bg-red-100 text-red-800'
                                }`}>
                                  {decision.outcome}
                                </span>
                                <span className="bg-gray-100 text-gray-700 px-2 py-1 rounded text-xs">
                                  {decision.vote}
                                </span>
                              </div>
                            </div>
                            <p className="text-sm text-gray-600">{decision.details}</p>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Concerns and Next Steps */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                      <div>
                        <h3 className="font-semibold text-gray-900 mb-3">Community Concerns</h3>
                        <ul className="space-y-2">
                          {selectedMeeting.analysis.publicConcerns.map((concern, idx) => (
                            <li key={idx} className="flex items-start text-sm">
                              <span className="w-2 h-2 bg-yellow-500 rounded-full mt-2 mr-3 flex-shrink-0"></span>
                              {concern}
                            </li>
                          ))}
                        </ul>
                      </div>

                      <div>
                        <h3 className="font-semibold text-gray-900 mb-3">Next Steps</h3>
                        <ul className="space-y-2">
                          {selectedMeeting.analysis.nextSteps.map((step, idx) => (
                            <li key={idx} className="flex items-start text-sm">
                              <span className="w-2 h-2 bg-green-500 rounded-full mt-2 mr-3 flex-shrink-0"></span>
                              {step}
                            </li>
                          ))}
                        </ul>
                      </div>
                    </div>

                    {/* Topics */}
                    <div>
                      <h3 className="font-semibold text-gray-900 mb-3">Main Topics</h3>
                      <div className="flex flex-wrap gap-2">
                        {selectedMeeting.analysis.mainTopics.map((topic, idx) => (
                          <span
                            key={idx}
                            className="bg-gray-100 text-gray-700 px-3 py-1 rounded-full text-sm"
                          >
                            {topic}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="text-center py-8">
                    <div className="text-gray-400 mb-4">
                      {getStatusIcon(selectedMeeting.status)}
                    </div>
                    <p className="text-gray-600">
                      {selectedMeeting.status === 'processing' ? 'Meeting is currently being processed...' :
                       selectedMeeting.status === 'failed' ? 'Processing failed for this meeting.' :
                       'No analysis available yet.'}
                    </p>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default AutonomousCB7Dashboard;