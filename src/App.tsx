import React, { useState, useRef } from 'react';
import { Upload, Play, Download, FileText, Brain, CheckCircle, AlertCircle, Loader, Computer, Zap, Shield } from 'lucide-react';
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
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [processingMode, setProcessingMode] = useState<'file' | 'youtube'>('file');

  const initialSteps: ProcessingStep[] = [
    { id: 'extract', name: 'Extract Audio', status: 'pending', message: 'Preparing audio extraction...' },
    { id: 'transcribe', name: 'Local Transcription', status: 'pending', message: 'Loading Whisper model...' },
    { id: 'analyze', name: 'AI Analysis', status: 'pending', message: 'Preparing local LLM...' },
    { id: 'complete', name: 'Generate Summary', status: 'pending', message: 'Finalizing results...' }
  ];

  const updateStep = (stepId: string, status: ProcessingStep['status'], message: string, duration?: string) => {
    setSteps(prev => prev.map(step => 
      step.id === stepId 
        ? { ...step, status, message, duration }
        : step
    ));
  };

  const simulateLocalProcessing = async () => {
    setIsProcessing(true);
    setSteps(initialSteps);
    setAnalysis(null);

    try {
      // Step 1: Audio Extraction
      updateStep('extract', 'processing', 'Extracting audio from video...');
      await new Promise(resolve => setTimeout(resolve, 3000));
      updateStep('extract', 'completed', 'Audio extracted successfully (127.3 MB)', '3.2s');

      // Step 2: Local Transcription
      updateStep('transcribe', 'processing', 'Running Whisper locally... (this may take a while)');
      await new Promise(resolve => setTimeout(resolve, 8000));
      updateStep('transcribe', 'completed', 'Transcription complete (42,891 words)', '18.4s');

      // Step 3: Local AI Analysis
      updateStep('analyze', 'processing', 'Analyzing with local Llama 3.1...');
      await new Promise(resolve => setTimeout(resolve, 6000));
      updateStep('analyze', 'completed', 'Analysis complete with local AI', '12.7s');

      // Step 4: Finalize
      updateStep('complete', 'processing', 'Generating final summary...');
      await new Promise(resolve => setTimeout(resolve, 2000));
      updateStep('complete', 'completed', 'Summary generated successfully!', '1.8s');

      // Set mock analysis results
      setAnalysis({
        title: "CB7 Full Board Meeting - October 2024",
        summary: "Community Board 7 addressed several key development projects and community concerns, with significant discussion around affordable housing and traffic safety improvements in the Upper West Side.",
        keyDecisions: [
          {
            item: "West 79th Street Bike Lane Extension",
            outcome: "Approved",
            vote: "11-4",
            details: "Approved 6-month pilot program with community feedback sessions"
          },
          {
            item: "Affordable Housing Development - Broadway & 84th",
            outcome: "Approved with Conditions",
            vote: "9-6", 
            details: "Approved with requirement for 30% affordable units and height reduction"
          },
          {
            item: "Riverside Park Concert Venue Expansion",
            outcome: "Rejected",
            vote: "4-11",
            details: "Rejected due to noise concerns and environmental impact"
          }
        ],
        publicConcerns: [
          "Increased construction noise affecting residential areas",
          "Need for more accessible playgrounds in Riverside Park", 
          "Traffic congestion during school pickup/dropoff times",
          "Rising commercial rents forcing local businesses to close"
        ],
        nextSteps: [
          "Schedule community workshop on bike lane implementation",
          "Request traffic study for Columbus Avenue corridor",
          "Form working group on small business preservation",
          "Coordinate with Parks Department on playground accessibility"
        ],
        sentiment: "Cautiously Optimistic",
        attendance: "15 board members, ~85 community members",
        mainTopics: ["Transportation", "Housing Development", "Parks & Recreation", "Small Business Support"],
        processingTime: "36.1 seconds"
      });

    } catch (error) {
      updateStep('analyze', 'error', 'Processing failed. Please try again.', '');
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
        return <CheckCircle className="step-icon" style={{color: '#38a169'}} />;
      case 'processing':
        return <Loader className="step-icon animate-spin" style={{color: '#3182ce'}} />;
      case 'error':
        return <AlertCircle className="step-icon" style={{color: '#e53e3e'}} />;
      default:
        return <div className="step-icon" style={{width: '1.25rem', height: '1.25rem', border: '2px solid #cbd5e0', borderRadius: '50%'}} />;
    }
  };

  const getSentimentClass = (sentiment: string) => {
    switch (sentiment) {
      case 'Positive': return 'sentiment-positive';
      case 'Cautiously Optimistic': return 'sentiment-optimistic';
      case 'Mixed': return 'sentiment-mixed';
      case 'Negative': return 'sentiment-negative';
      default: return 'sentiment-mixed';
    }
  };

  if (analysis) {
    return (
      <div className="app-container">
        <div className="max-width-container">
          {/* Header */}
          <div className="header">
            <div className="flex justify-between align-center mb-4">
              <h1 className="flex align-center gap-3">
                <Computer size={32} style={{color: '#38a169'}} />
                Meeting Analysis Complete
              </h1>
              <button
                onClick={resetProcessor}
                className="btn btn-primary"
              >
                Process Another Meeting
              </button>
            </div>
            
            <div className="header-stats">
              <div className="stat-card">
                <Shield size={24} style={{color: '#38a169', margin: '0 auto 0.5rem'}} />
                <div className="stat-number">100% Private</div>
                <div className="stat-label">Processed Locally</div>
              </div>
              <div className="stat-card">
                <Zap size={24} style={{color: '#3182ce', margin: '0 auto 0.5rem'}} />
                <div className="stat-number">{analysis.processingTime}</div>
                <div className="stat-label">Processing Time</div>
              </div>
              <div className="stat-card">
                <FileText size={24} style={{color: '#805ad5', margin: '0 auto 0.5rem'}} />
                <div className="stat-number">$0.00</div>
                <div className="stat-label">Processing Cost</div>
              </div>
              <div className="stat-card">
                <Brain size={24} style={{color: '#d69e2e', margin: '0 auto 0.5rem'}} />
                <div className="stat-number">{analysis.sentiment}</div>
                <div className="stat-label">Meeting Sentiment</div>
              </div>
            </div>
          </div>

          {/* Meeting Summary */}
          <div className="card">
            <h2 className="card-title" style={{fontSize: '1.5rem', marginBottom: '1rem'}}>{analysis.title}</h2>
            <p style={{color: '#4a5568', fontSize: '1.125rem', lineHeight: '1.6', marginBottom: '1rem'}}>{analysis.summary}</p>
            <div style={{fontSize: '0.875rem', color: '#718096'}}>
              <strong>Attendance:</strong> {analysis.attendance}
            </div>
          </div>

          {/* Key Decisions */}
          <div className="card">
            <h3 className="analysis-title">Key Decisions & Votes</h3>
            <div className="grid gap-4">
              {analysis.keyDecisions.map((decision, idx) => (
                <div key={idx} className="decision-item">
                  <div className="decision-header">
                    <h4 className="decision-title">{decision.item}</h4>
                    <div className="decision-badges">
                      {decision.outcome.includes('Approved') ? (
                        <CheckCircle size={20} style={{color: '#38a169'}} />
                      ) : (
                        <AlertCircle size={20} style={{color: '#e53e3e'}} />
                      )}
                      <span className={`badge ${decision.outcome.includes('Approved') ? 'badge-success' : 'badge-error'}`}>
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

          {/* Concerns and Next Steps */}
          <div className="grid grid-2">
            <div className="card">
              <h3 className="analysis-title">Community Concerns</h3>
              <ul className="list">
                {analysis.publicConcerns.map((concern, idx) => (
                  <li key={idx} className="list-item">
                    <span className="list-bullet list-bullet-yellow"></span>
                    <span style={{color: '#4a5568', fontSize: '0.875rem'}}>{concern}</span>
                  </li>
                ))}
              </ul>
            </div>

            <div className="card">
              <h3 className="analysis-title">Next Steps</h3>
              <ul className="list">
                {analysis.nextSteps.map((step, idx) => (
                  <li key={idx} className="list-item">
                    <span className="list-bullet list-bullet-green"></span>
                    <span style={{color: '#4a5568', fontSize: '0.875rem'}}>{step}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="app-container">
      <div className="max-width-container">
        {/* Header */}
        <div className="text-center mb-4">
          <h1 className="flex align-center justify-center gap-3" style={{fontSize: '2.5rem', fontWeight: '700', color: '#1a202c', marginBottom: '1rem'}}>
            <Computer size={40} style={{color: '#38a169'}} />
            Community Board Meetings Analyzer
          </h1>
          <p style={{color: '#718096', fontSize: '1.125rem'}}>Turn 1 hour meetings into quick 5-minute summaries with key points!</p>
          
          <div className="flex align-center justify-center gap-4 mt-4" style={{fontSize: '0.875rem'}}>
            <div className="flex align-center gap-1" style={{color: '#38a169'}}>
              <Shield size={16} />
              100% Private
            </div>
          </div>
        </div>

        {/* Input Method Selection */}
        <div className="card">
          <div className="flex align-center justify-center mb-4">
            <div style={{display: 'flex', background: '#f7fafc', borderRadius: '0.5rem', padding: '0.25rem'}}>
              <button
                onClick={() => setProcessingMode('file')}
                className={`btn ${processingMode === 'file' ? 'btn-primary' : 'btn-secondary'}`}
                style={{fontSize: '0.875rem', padding: '0.5rem 1rem'}}
              >
                Upload File
              </button>
              <button
                onClick={() => setProcessingMode('youtube')}
                className={`btn ${processingMode === 'youtube' ? 'btn-primary' : 'btn-secondary'}`}
                style={{fontSize: '0.875rem', padding: '0.5rem 1rem'}}
              >
                YouTube URL
              </button>
            </div>
          </div>

          {processingMode === 'file' ? (
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
                <div style={{display: 'flex', flexDirection: 'column', gap: '0.75rem'}}>
                  <CheckCircle size={48} style={{color: '#38a169', margin: '0 auto'}} />
                  <div>
                    <p style={{fontWeight: '500', color: '#1a202c'}}>{file.name}</p>
                    <p style={{fontSize: '0.875rem', color: '#718096'}}>
                      {(file.size / (1024 * 1024)).toFixed(2)} MB
                    </p>
                  </div>
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    className="btn btn-secondary"
                    style={{fontSize: '0.875rem'}}
                  >
                    Choose different file
                  </button>
                </div>
              ) : (
                <div style={{display: 'flex', flexDirection: 'column', gap: '0.75rem'}}>
                  <Upload size={48} style={{color: '#a0aec0', margin: '0 auto'}} />
                  <div>
                    <p style={{fontSize: '1.125rem', fontWeight: '500', color: '#1a202c'}}>
                      Drop your meeting video here
                    </p>
                    <p style={{color: '#718096'}}>
                      or{' '}
                      <button
                        onClick={() => fileInputRef.current?.click()}
                        style={{color: '#3182ce', fontWeight: '500', background: 'none', border: 'none', cursor: 'pointer'}}
                      >
                        browse files
                      </button>
                    </p>
                  </div>
                  <p style={{fontSize: '0.875rem', color: '#a0aec0'}}>
                    Supports MP4, MOV, AVI, MP3, WAV files
                  </p>
                </div>
              )}
            </div>
          ) : (
            <div style={{display: 'flex', flexDirection: 'column', gap: '1rem'}}>
              <input
                type="url"
                placeholder="https://www.youtube.com/watch?v=..."
                value={youtubeUrl}
                onChange={(e) => setYoutubeUrl(e.target.value)}
                className="input"
              />
              <p style={{fontSize: '0.875rem', color: '#718096', textAlign: 'center'}}>
                Paste any YouTube URL from CB7's channel
              </p>
            </div>
          )}

          <button
            onClick={simulateLocalProcessing}
            disabled={(!file && !youtubeUrl) || isProcessing}
            className="btn btn-success"
            style={{width: '100%', marginTop: '1.5rem', justifyContent: 'center'}}
          >
            {isProcessing ? (
              <>
                <Loader size={20} className="animate-spin" />
                Processing...
              </>
            ) : (
              <>
                <Play size={20} />
                Start Processing
              </>
            )}
          </button>
        </div>

        {/* Processing Steps */}
        {steps.length > 0 && (
          <div className="card">
            <h3 className="analysis-title">Local Processing Pipeline</h3>
            
            <div style={{display: 'flex', flexDirection: 'column', gap: '1rem'}}>
              {steps.map((step) => (
                <div key={step.id} className="processing-step">
                  <div style={{marginRight: '1rem'}}>
                    {getStepIcon(step)}
                  </div>
                  <div style={{flex: 1}}>
                    <div className="flex justify-between align-center">
                      <h4 className="step-title" style={{
                        color: step.status === 'completed' ? '#38a169' :
                               step.status === 'processing' ? '#3182ce' :
                               step.status === 'error' ? '#e53e3e' : '#4a5568'
                      }}>
                        {step.name}
                      </h4>
                      {step.duration && (
                        <span className="step-duration">
                          {step.duration}
                        </span>
                      )}
                    </div>
                    <p className="step-description" style={{
                      color: step.status === 'error' ? '#e53e3e' : '#718096'
                    }}>
                      {step.message}
                    </p>
                  </div>
                </div>
              ))}
            </div>

            {isProcessing && (
              <div style={{marginTop: '1.5rem', background: '#f7fafc', borderRadius: '0.5rem', padding: '1rem'}}>
                <div className="flex align-center gap-2" style={{fontSize: '0.875rem', color: '#718096'}}>
                  <Computer size={16} />
                  Processing on your computer - no data sent to external servers
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