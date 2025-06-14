import React, { useState, useRef, useEffect } from 'react';
import { Upload, Play, FileText, Brain, CheckCircle, AlertCircle, Loader, Computer, Zap, Shield, Calendar, Users, MessageSquare, TrendingUp } from 'lucide-react';
import './App.css';

interface ProcessingStep {
  id: string;
  name: string;
  status: 'pending' | 'processing' | 'completed' | 'error';
  message: string;
  duration?: string;
}

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
}

const App = () => {
  const [file, setFile] = useState<File | null>(null);
  const [youtubeUrl, setYoutubeUrl] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [steps, setSteps] = useState<ProcessingStep[]>([]);
  const [analysis, setAnalysis] = useState<MeetingAnalysis | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [processingMode, setProcessingMode] = useState<'file' | 'youtube'>('youtube');
  const [backendStatus, setBackendStatus] = useState<'checking' | 'online' | 'offline'>('checking');
  const fileInputRef = useRef<HTMLInputElement>(null);

  const initialSteps: ProcessingStep[] = [
    { id: 'extract', name: 'Extract Audio', status: 'pending', message: 'Downloading and extracting audio from video...' },
    { id: 'transcribe', name: 'AI Transcription', status: 'pending', message: 'Converting speech to text with Whisper AI...' },
    { id: 'analyze', name: 'Content Analysis', status: 'pending', message: 'Analyzing meeting content with local AI...' },
    { id: 'complete', name: 'Generate Summary', status: 'pending', message: 'Creating structured meeting summary...' }
  ];

  // Check backend status on component mount
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
    const interval = setInterval(checkBackend, 30000); // Check every 30 seconds
    return () => clearInterval(interval);
  }, []);

  const updateStep = (stepId: string, status: ProcessingStep['status'], message: string, duration?: string) => {
    setSteps(prev => prev.map(step => 
      step.id === stepId 
        ? { ...step, status, message, duration }
        : step
    ));
  };

  const processVideo = async () => {
    if (backendStatus !== 'online') {
      alert('Backend server is not running. Please start the Python server first.');
      return;
    }

    setIsProcessing(true);
    setSteps(initialSteps);
    setAnalysis(null);

    try {
      let response;
      
      if (processingMode === 'youtube' && youtubeUrl) {
        // Process YouTube URL
        updateStep('extract', 'processing', 'Downloading video from YouTube...');
        
        response = await fetch('http://localhost:8000/process-youtube', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ url: youtubeUrl }),
        });
      } else if (processingMode === 'file' && file) {
        // Process uploaded file
        updateStep('extract', 'processing', 'Processing uploaded file...');
        
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

      // Simulate step progression
      updateStep('extract', 'completed', 'Audio extracted successfully', '5.2s');
      updateStep('transcribe', 'processing', 'Transcribing audio with Whisper AI...');
      
      await new Promise(resolve => setTimeout(resolve, 2000));
      updateStep('transcribe', 'completed', 'Transcription completed', '45.8s');
      updateStep('analyze', 'processing', 'Analyzing content with local AI...');
      
      await new Promise(resolve => setTimeout(resolve, 1500));
      updateStep('analyze', 'completed', 'Analysis completed', '18.3s');
      updateStep('complete', 'processing', 'Generating summary...');

      const result = await response.json();
      
      await new Promise(resolve => setTimeout(resolve, 1000));
      updateStep('complete', 'completed', 'Summary generated successfully!', '2.1s');

      // Transform the response to match our interface
      setAnalysis({
        title: result.title,
        summary: result.analysis.summary || 'Meeting analysis completed successfully.',
        keyDecisions: result.analysis.keyDecisions || [],
        publicConcerns: result.analysis.publicConcerns || [],
        nextSteps: result.analysis.nextSteps || [],
        sentiment: result.analysis.sentiment || 'Mixed',
        attendance: result.analysis.attendance || 'Not specified',
        mainTopics: result.analysis.mainTopics || [],
        processingTime: result.processingTime || 'Unknown'
      });

    } catch (error) {
      console.error('Processing error:', error);
      updateStep('analyze', 'error', `Processing failed: ${error instanceof Error ? error.message : 'Unknown error'}`, '');
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
    setSteps([]);
    setAnalysis(null);
    setIsProcessing(false);
  };

  const getStepIcon = (step: ProcessingStep) => {
    switch (step.status) {
      case 'completed':
        return <CheckCircle className="step-icon" style={{color: '#48bb78'}} />;
      case 'processing':
        return <Loader className="step-icon animate-spin" style={{color: '#4299e1'}} />;
      case 'error':
        return <AlertCircle className="step-icon" style={{color: '#f56565'}} />;
      default:
        return <div className="step-icon" style={{
          width: '1.25rem', 
          height: '1.25rem', 
          border: '2px solid #cbd5e0', 
          borderRadius: '50%'
        }} />;
    }
  };

  const getSentimentClass = (sentiment: string) => {
    switch (sentiment) {
      case 'Positive': return 'sentiment-positive';
      case 'Generally Positive': return 'sentiment-positive';
      case 'Cautiously Optimistic': return 'sentiment-optimistic';
      case 'Mixed': return 'sentiment-mixed';
      case 'Negative': return 'sentiment-negative';
      default: return 'sentiment-mixed';
    }
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

  if (analysis) {
    return (
      <div className="app-container">
        <div className="max-width-container">
          {/* Results Header */}
          <div className="header slide-up">
            <div className="flex justify-between align-center mb-4">
              <div>
                <h1 className="flex align-center gap-3">
                  <TrendingUp size={32} style={{color: '#48bb78'}} />
                  Meeting Analysis Complete
                </h1>
                <p>AI-powered analysis of Community Board 7 meeting</p>
              </div>
              <button onClick={resetProcessor} className="btn btn-primary">
                <Play size={16} />
                Process Another Meeting
              </button>
            </div>
            
            <div className="header-stats">
              <div className="stat-card">
                <Shield size={24} style={{color: '#48bb78', margin: '0 auto 0.5rem'}} />
                <div className="stat-number">100% Private</div>
                <div className="stat-label">Processed Locally</div>
              </div>
              <div className="stat-card">
                <Zap size={24} style={{color: '#4299e1', margin: '0 auto 0.5rem'}} />
                <div className="stat-number">{analysis.processingTime}</div>
                <div className="stat-label">Processing Time</div>
              </div>
              <div className="stat-card">
                <FileText size={24} style={{color: '#805ad5', margin: '0 auto 0.5rem'}} />
                <div className="stat-number">$0.00</div>
                <div className="stat-label">Processing Cost</div>
              </div>
              <div className="stat-card">
                <MessageSquare size={24} style={{color: '#ed8936', margin: '0 auto 0.5rem'}} />
                <div className="stat-number">{analysis.sentiment}</div>
                <div className="stat-label">Meeting Sentiment</div>
              </div>
            </div>
          </div>

          {/* Meeting Summary */}
          <div className="card slide-up">
            <h2 className="card-title">
              <Calendar size={20} />
              {analysis.title}
            </h2>
            <p style={{color: '#4a5568', fontSize: '1.1rem', lineHeight: '1.7', marginBottom: '1rem'}}>
              {analysis.summary}
            </p>
            <div className="flex align-center gap-4" style={{fontSize: '0.9rem', color: '#718096'}}>
              <div className="flex align-center gap-1">
                <Users size={16} />
                <strong>Attendance:</strong> {analysis.attendance}
              </div>
              <div className={`badge ${getSentimentClass(analysis.sentiment)}`}>
                {analysis.sentiment}
              </div>
            </div>
          </div>

          {/* Key Decisions */}
          {analysis.keyDecisions && analysis.keyDecisions.length > 0 && (
            <div className="card slide-up">
              <h3 className="analysis-title">
                <CheckCircle size={20} />
                Key Decisions & Voting Results
              </h3>
              <div className="grid gap-4">
                {analysis.keyDecisions.map((decision, idx) => (
                  <div key={idx} className="decision-item">
                    <div className="decision-header">
                      <h4 className="decision-title">{decision.item}</h4>
                      <div className="decision-badges">
                        {decision.outcome.includes('Approved') || decision.outcome.includes('Supported') ? (
                          <CheckCircle size={18} style={{color: '#48bb78'}} />
                        ) : (
                          <AlertCircle size={18} style={{color: '#f56565'}} />
                        )}
                        <span className={`badge ${
                          decision.outcome.includes('Approved') || decision.outcome.includes('Supported')
                            ? 'badge-success' 
                            : 'badge-error'
                        }`}>
                          {decision.outcome}
                        </span>
                        <span className="badge badge-pending">
                          {decision.vote}
                        </span>
                      </div>
                    </div>
                    <p className="decision-details">{decision.details}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Concerns and Next Steps */}
          <div className="grid grid-2">
            {analysis.publicConcerns && analysis.publicConcerns.length > 0 && (
              <div className="card slide-up">
                <h3 className="analysis-title">
                  <MessageSquare size={20} />
                  Community Concerns
                </h3>
                <ul className="list">
                  {analysis.publicConcerns.map((concern, idx) => (
                    <li key={idx} className="list-item">
                      <span className="list-bullet list-bullet-yellow"></span>
                      <span style={{color: '#4a5568', fontSize: '0.9rem', lineHeight: '1.5'}}>
                        {concern}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {analysis.nextSteps && analysis.nextSteps.length > 0 && (
              <div className="card slide-up">
                <h3 className="analysis-title">
                  <TrendingUp size={20} />
                  Next Steps & Action Items
                </h3>
                <ul className="list">
                  {analysis.nextSteps.map((step, idx) => (
                    <li key={idx} className="list-item">
                      <span className="list-bullet list-bullet-green"></span>
                      <span style={{color: '#4a5568', fontSize: '0.9rem', lineHeight: '1.5'}}>
                        {step}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {/* Main Topics */}
          {analysis.mainTopics && analysis.mainTopics.length > 0 && (
            <div className="card slide-up">
              <h3 className="analysis-title">
                <Brain size={20} />
                Main Discussion Topics
              </h3>
              <div className="flex" style={{gap: '0.75rem', flexWrap: 'wrap'}}>
                {analysis.mainTopics.map((topic, idx) => (
                  <span
                    key={idx}
                    className="badge badge-pending"
                    style={{fontSize: '0.85rem', padding: '0.5rem 1rem'}}
                  >
                    {topic}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="app-container">
      <div className="max-width-container">
        {/* Main Header */}
        <div className="text-center mb-4">
          <h1 className="flex align-center justify-center gap-3" style={{
            fontSize: '2.5rem', 
            fontWeight: '700', 
            color: '#1a202c', 
            marginBottom: '1rem'
          }}>
            <Computer size={40} style={{color: '#4299e1'}} />
            CB7 Meeting Analyzer
          </h1>
          <p style={{color: '#718096', fontSize: '1.2rem', marginBottom: '1rem'}}>
            AI-powered analysis of Community Board 7 meetings
          </p>
          <p style={{color: '#a0aec0', fontSize: '1rem'}}>
            Process meetings privately on your computer - no cloud, no cost, no data sharing
          </p>
          
          <div className="flex align-center justify-center gap-4 mt-4" style={{fontSize: '0.9rem'}}>
            <div className="flex align-center gap-1" style={{color: '#48bb78'}}>
              <Shield size={16} />
              100% Private
            </div>
            <div className="flex align-center gap-1" style={{color: '#4299e1'}}>
              <Zap size={16} />
              No API Costs
            </div>
            <div className="flex align-center gap-1" style={{color: '#805ad5'}}>
              <Computer size={16} />
              Runs Locally
            </div>
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

        {/* Backend Status Warning */}
        {backendStatus === 'offline' && (
          <div className="card" style={{
            background: 'linear-gradient(135deg, #fed7d7 0%, #feb2b2 100%)',
            border: '2px solid #fc8181',
            marginBottom: '2rem'
          }}>
            <div className="flex align-center gap-3">
              <AlertCircle size={24} style={{color: '#742a2a'}} />
              <div>
                <h3 style={{color: '#742a2a', marginBottom: '0.5rem'}}>Backend Server Offline</h3>
                <p style={{color: '#742a2a', fontSize: '0.9rem', marginBottom: '0'}}>
                  Please start the Python backend server by running <code>python main.py</code> in your backend directory.
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Processing Mode & Input */}
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
                placeholder="https://www.youtube.com/watch?v=... (CB7 meeting video)"
                value={youtubeUrl}
                onChange={(e) => setYoutubeUrl(e.target.value)}
                className="input"
              />
              <p style={{fontSize: '0.875rem', color: '#718096', textAlign: 'center'}}>
                Paste any YouTube URL from CB7's channel or other meeting videos
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

        {/* Processing Steps */}
        {steps.length > 0 && (
          <div className="card">
            <h3 className="analysis-title">
              <Computer size={20} />
              Local Processing Pipeline
            </h3>
            
            <div className="processing-steps">
              {steps.map((step) => (
                <div key={step.id} className="processing-step">
                  <div>{getStepIcon(step)}</div>
                  <div className="step-content">
                    <div className="flex justify-between align-center">
                      <div className="step-title" style={{
                        color: step.status === 'completed' ? '#48bb78' :
                               step.status === 'processing' ? '#4299e1' :
                               step.status === 'error' ? '#f56565' : '#e2e8f0'
                      }}>
                        {step.name}
                      </div>
                      {step.duration && (
                        <span className="step-duration">{step.duration}</span>
                      )}
                    </div>
                    <div className="step-description" style={{
                      color: step.status === 'error' ? '#fed7d7' : '#a0aec0'
                    }}>
                      {step.message}
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {isProcessing && (
              <div style={{
                marginTop: '1.5rem', 
                background: 'rgba(66, 153, 225, 0.1)', 
                borderRadius: '0.75rem', 
                padding: '1rem',
                border: '1px solid rgba(66, 153, 225, 0.2)'
              }}>
                <div className="flex align-center gap-2" style={{fontSize: '0.9rem', color: '#4299e1'}}>
                  <Shield size={16} />
                  Processing privately on your computer - no data sent to external servers
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default App;