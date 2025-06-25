import React, { useState, useRef, useEffect } from 'react';
import { Upload, Brain, CheckCircle, Loader, ArrowLeft } from 'lucide-react';
import './App.css';
import MarkdownRenderer from './components/MarkdownRenderer';
import Navbar from './components/Navbar';
import MeetingList from './components/MeetingList';

interface MeetingAnalysis {
  title: string;
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
  processingTime: string;
  summary_markdown?: string;
}

const App = () => {
  const [file, setFile] = useState<File | null>(null);
  const [youtubeUrl, setYoutubeUrl] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [analysis, setAnalysis] = useState<MeetingAnalysis | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [processingMode, setProcessingMode] = useState<'file' | 'youtube'>('youtube');
  const [backendStatus, setBackendStatus] = useState<'checking' | 'online' | 'offline'>('checking');
  const [currentView, setCurrentView] = useState<'analyzer' | 'meetings'>('analyzer');
  const [selectedCB, setSelectedCB] = useState<number | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const checkBackend = async () => {
      try {
        const response = await fetch('http://localhost:8000/health');
        if (response.ok) {
          setBackendStatus('online');
        } else {
          setBackendStatus('offline');
        }
      } catch (error) {
        setBackendStatus('offline');
      }
    };

    checkBackend();
  }, []);

  const handleBoardSelect = (boardNumber: number | null) => {
    if (boardNumber === null) {
      setCurrentView('analyzer');
      setSelectedCB(null);
      setAnalysis(null);
    } else {
      setCurrentView('meetings');
      setSelectedCB(boardNumber);
      setAnalysis(null);
    }
  };

  const generateMarkdownFromAnalysis = (analysis: MeetingAnalysis): string => {
    let markdown = `# Community Board Meeting, Analyzed on: ${new Date().toISOString().split('T')[0]}\n\n`;
    
    markdown += `## Meeting Overview\n\n`;
    markdown += `${analysis.summary}\n\n`;
    
    markdown += `**Overall Sentiment:** ${analysis.sentiment}\n`;
    markdown += `**Attendance:** ${analysis.attendance}\n\n`;
    
    if (analysis.keyDecisions && analysis.keyDecisions.length > 0) {
      markdown += `## Key Decisions\n\n`;
      analysis.keyDecisions.forEach((decision) => {
        markdown += `### ${decision.item}\n`;
        markdown += `- **Outcome:** ${decision.outcome}\n`;
        if (decision.vote) markdown += `- **Vote:** ${decision.vote}\n`;
        if (decision.details) markdown += `- **Details:** ${decision.details}\n`;
        markdown += '\n';
      });
    }
    
    if (analysis.mainTopics && analysis.mainTopics.length > 0) {
      markdown += `## Main Topics Discussed\n\n`;
      analysis.mainTopics.forEach((topic, idx) => {
        markdown += `${idx + 1}. ${topic}\n`;
      });
      markdown += '\n';
    }
    
    if (analysis.publicConcerns && analysis.publicConcerns.length > 0) {
      markdown += `## Public Concerns\n\n`;
      analysis.publicConcerns.forEach((concern) => {
        markdown += `- ${concern}\n`;
      });
      markdown += '\n';
    }
    
    if (analysis.nextSteps && analysis.nextSteps.length > 0) {
      markdown += `## Next Steps / Action Items\n\n`;
      analysis.nextSteps.forEach((step) => {
        markdown += `- ${step}\n`;
      });
      markdown += '\n';
    }
    
    return markdown;
  };

  const handleSelectMeeting = (meeting: any) => {
    // Show the meeting analysis
    if (meeting.analysis) {
      const analysisData = {
        title: meeting.title,
        summary: meeting.analysis.summary || '',
        keyDecisions: meeting.analysis.keyDecisions || [],
        publicConcerns: meeting.analysis.publicConcerns || [],
        nextSteps: meeting.analysis.nextSteps || [],
        sentiment: meeting.analysis.sentiment || 'Mixed',
        attendance: meeting.analysis.attendance || 'Not specified',
        mainTopics: meeting.analysis.mainTopics || [],
        processingTime: 'Previously processed',
        summary_markdown: meeting.analysis.summary_markdown
      };
      
      // If no markdown exists, generate it from the analysis data
      if (!analysisData.summary_markdown) {
        analysisData.summary_markdown = generateMarkdownFromAnalysis(analysisData);
      }
      
      setAnalysis(analysisData);
      setCurrentView('analyzer'); // Switch to analyzer view to show the analysis
    }
  };

  const processVideo = async () => {
    if (backendStatus !== 'online') {
      alert('Server is not active');
      return;
    }

    setIsProcessing(true);
    setAnalysis(null);

    try {
      let response;
      
      if (processingMode === 'youtube' && youtubeUrl) {        
        response = await fetch('http://localhost:8000/process-youtube', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ url: youtubeUrl }),
        });
      } else if (processingMode === 'file' && file) {
        const formData = new FormData();
        formData.append('file', file);
        
        response = await fetch('http://localhost:8000/process-file', {
          method: 'POST',
          body: formData,
        });
      } else {
        throw new Error('No file or URL provided');
      }

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Processing failed');
      }

      const result = await response.json();

      setAnalysis({
        title: result.title,
        summary: result.analysis.summary || 'Meeting analysis completed successfully.',
        keyDecisions: result.analysis.keyDecisions || [],
        publicConcerns: result.analysis.publicConcerns || [],
        nextSteps: result.analysis.nextSteps || [],
        sentiment: result.analysis.sentiment || 'Mixed',
        attendance: result.analysis.attendance || 'Not specified',
        mainTopics: result.analysis.mainTopics || [],
        processingTime: result.processingTime || 'Unknown',
        summary_markdown: result.summary_markdown
      });

    } catch (error: unknown) {
      console.error('Processing error:', error);
    
      const message = error instanceof Error ? error.message : String(error);
      alert(`Processing failed: ${message}`);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const droppedFile = e.dataTransfer.files[0];
      if (droppedFile.type.startsWith('video/') || droppedFile.type.startsWith('audio/')) {
        setFile(droppedFile);
        setProcessingMode('file');
      } else {
        alert('Please upload a video or audio file.');
      }
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
    }
  };

  const resetProcessor = () => {
    setFile(null);
    setYoutubeUrl('');
    setAnalysis(null);
    setIsProcessing(false);
  };

  const getBackendStatusColor = () => {
    switch (backendStatus) {
      case 'online': return '#48bb78';
      case 'offline': return '#f56565';
      default: return '#ed8936';
    }
  };

  const getBackendStatusText = () => {
    switch (backendStatus) {
      case 'online': return 'Server Online';
      case 'offline': return 'Server Offline';
      default: return 'Checking...';
    }
  };

  const extractCBNumber = (title: string): string => {
    const patterns = [
      /CB\s*(\d+)/i,
      /Community Board\s*(\d+)/i,
      /Community Board\s*#(\d+)/i,
      /MCB\s*(\d+)/i,
      /Board\s*(\d+)/i,
      /District\s*(\d+)/i,
    ];
    
    for (const pattern of patterns) {
      const match = title.match(pattern);
      if (match) return match[1];
    }
    
    const numberMatch = title.match(/\b([1-9]|1[0-2])\b/);
    if (numberMatch && title.toLowerCase().includes('board')) {
      return numberMatch[1];
    }
    
    const cbNames: { [key: string]: string } = {
      'manhattan': '?',
      'upper west side': '7',
      'upper east side': '8',
      'harlem': '9',
      'central harlem': '10',
      'east harlem': '11',
      'washington heights': '12',
    };
    
    const titleLower = title.toLowerCase();
    for (const [area, number] of Object.entries(cbNames)) {
      if (titleLower.includes(area)) return number;
    }
    
    return '';
  };

  // Render analysis view
  if (analysis && currentView === 'analyzer') {
    const cbNumber = extractCBNumber(analysis.title);
    
    return (
      <div style={{ minHeight: '100vh', background: '#f7fafc' }}>
        <Navbar onBoardSelect={handleBoardSelect} currentView={currentView} />
        
        <div className="app-container" style={{ marginTop: 0, background: '#f7fafc' }}>
          <div className="max-width-container">
            <div className="slide-up" style={{ textAlign: 'left' }}>
              <h1 style={{
                fontSize: '2.5rem',
                fontWeight: '700',
                color: '#1a202c',
                marginBottom: '1rem',
                textAlign: 'left'
              }}>
                Community Board {cbNumber} Meeting
              </h1>

              <h2 style={{
                fontSize: '1.875rem',
                fontWeight: '600',
                color: '#2d3748',
                marginBottom: '1.5rem',
                textAlign: 'left'
              }}>
                {analysis.title}
              </h2>

              <MarkdownRenderer markdown={analysis.summary_markdown || generateMarkdownFromAnalysis(analysis)} />

              <div style={{ marginTop: '3rem' }}>
                <button onClick={resetProcessor} className="btn btn-primary">
                  <ArrowLeft size={16} />
                  Process Another Meeting
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Render meeting list view
  if (currentView === 'meetings' && selectedCB) {
    return (
      <div style={{ minHeight: '100vh', background: '#f7fafc' }}>
        <Navbar onBoardSelect={handleBoardSelect} currentView={currentView} />
        <MeetingList cbNumber={selectedCB} onSelectMeeting={handleSelectMeeting} />
      </div>
    );
  }

  // Render analyzer view
  return (
    <div style={{ minHeight: '100vh', background: '#f7fafc' }}>
      <Navbar onBoardSelect={handleBoardSelect} currentView={currentView} />
      
      <div className="app-container" style={{ marginTop: 0, background: '#f7fafc' }}>
        <div className="max-width-container">
          <div className="text-center mb-4">
            <h1 className="flex align-center justify-center gap-3" style={{
              fontSize: '2.5rem', 
              fontWeight: '700', 
              color: '#1a202c', 
              marginBottom: '1rem'
            }}>
              <img src='/logo.png' width={50} height={50} alt="CB Analyzer" />
              CB Meetings Analyzer
            </h1>
            <p style={{color: '#718096', fontSize: '1.2rem', marginBottom: '1rem'}}>
              AI-powered analysis of Community Board meetings
            </p>

            <div className="flex align-center justify-center gap-4 mt-4" style={{fontSize: '0.9rem'}}>
              <div className="flex align-center gap-1" style={{color: getBackendStatusColor()}}>
                <div style={{
                  width: '8px', 
                  height: '8px', 
                  borderRadius: '50%', 
                  backgroundColor: getBackendStatusColor()
                }} />
                {getBackendStatusText()}
              </div>
            </div>
          </div>

          <div className="card">
            <div className="flex align-center justify-center mb-4">
              <div className="mode-selector">
                <button
                  onClick={() => setProcessingMode('youtube')}
                  className={`mode-button ${processingMode === 'youtube' ? 'active' : ''}`}
                >
                  YouTube URL
                </button>
                <button
                  onClick={() => setProcessingMode('file')}
                  className={`mode-button ${processingMode === 'file' ? 'active' : ''}`}
                >
                  Upload File
                </button>
              </div>
            </div>

            {processingMode === 'youtube' ? (
              <div style={{display: 'flex', flexDirection: 'column', gap: '1rem'}}>
                <input
                  type="url"
                  placeholder="https://www.youtube.com/watch?v=... (CB meeting video)"
                  value={youtubeUrl}
                  onChange={(e) => setYoutubeUrl(e.target.value)}
                  className="input"
                />
                <p style={{fontSize: '0.875rem', color: '#718096', textAlign: 'center'}}>
                  Paste any YouTube URL from any CB channel or other meeting videos
                </p>
              </div>
            ) : (
              <div
                className={`upload-area ${dragActive ? 'active' : ''} ${file ? 'success' : ''}`}
                onDragEnter={handleDrag}
                onDragLeave={handleDrag}
                onDragOver={handleDrag}
                onDrop={handleDrop}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="video/*,audio/*"
                  onChange={handleFileSelect}
                  style={{display: 'none'}}
                />
                
                {file ? (
                  <div style={{display: 'flex', flexDirection: 'column', gap: '1rem', alignItems: 'center'}}>
                    <CheckCircle size={48} style={{color: '#48bb78'}} />
                    <div style={{textAlign: 'center'}}>
                      <p style={{fontWeight: '600', color: '#1a202c', fontSize: '1.1rem'}}>{file.name}</p>
                      <p style={{fontSize: '0.9rem', color: '#718096', marginTop: '0.25rem'}}>
                        {(file.size / (1024 * 1024)).toFixed(2)} MB
                      </p>
                    </div>
                    <button
                      onClick={() => fileInputRef.current?.click()}
                      className="btn btn-secondary"
                    >
                      Choose Different File
                    </button>
                  </div>
                ) : (
                  <div style={{display: 'flex', flexDirection: 'column', gap: '1rem', alignItems: 'center'}}>
                    <Upload size={48} style={{color: '#a0aec0'}} />
                    <div style={{textAlign: 'center'}}>
                      <p style={{fontSize: '1.2rem', fontWeight: '600', color: '#1a202c', marginBottom: '0.5rem'}}>
                        Drop your meeting video here
                      </p>
                      <p style={{color: '#718096'}}>
                        or{' '}
                        <button
                          onClick={() => fileInputRef.current?.click()}
                          style={{
                            color: '#4299e1', 
                            fontWeight: '500', 
                            background: 'none', 
                            border: 'none', 
                            cursor: 'pointer',
                            textDecoration: 'underline'
                          }}
                        >
                          browse files
                        </button>
                      </p>
                    </div>
                    <p style={{fontSize: '0.875rem', color: '#a0aec0'}}>
                      Supports MP4, MOV, AVI, MP3, WAV files (up to 2GB)
                    </p>
                  </div>
                )}
              </div>
            )}

            <button
              onClick={processVideo}
              disabled={(!file && !youtubeUrl) || isProcessing || backendStatus !== 'online'}
              className="btn btn-success"
              style={{width: '100%', marginTop: '2rem', padding: '1rem'}}
            >
              {isProcessing ? (
                <>
                  <Loader size={20} className="animate-spin" />
                  Processing Meeting...
                </>
              ) : (
                <>
                  <Brain size={20} />
                  Start AI Analysis
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default App;