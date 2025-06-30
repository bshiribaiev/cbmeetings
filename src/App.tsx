import React, { useState, useRef, useEffect } from 'react';
import { Brain, Loader, ArrowLeft, Youtube } from 'lucide-react';
import './App.css';
import MarkdownRenderer from './components/MarkdownRenderer';
import Navbar from './components/Navbar';
import MeetingList from './components/MeetingList';
import SummaryRender from './components/SummaryRender';

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
  summary_data?: any;
  cb_number?: number;
  url?: string;
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
        if (response.ok) setBackendStatus('online');
        else setBackendStatus('offline');
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
        response = await fetch('http://localhost:8000/process-youtube-async', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
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
        throw new Error(errorData.detail || errorData.message || 'Processing failed');
      }

      const result = await response.json();

      if (result.analysis) {
        setAnalysis({
          ...result.analysis,
          title: result.title,
          url: result.url, // Make sure URL is passed from backend if available
          processingTime: result.processingTime || 'Unknown',
        });
      } else if (result.success && result.message) {
        alert(result.message);
        resetProcessor();
      } else {
        throw new Error("Received an unexpected response from the server.");
      }

    } catch (error) {
      console.error('Processing error:', error);
      alert(`Processing failed: ${error instanceof Error ? error.message : 'Unknown error'}`);
    } finally {
      setIsProcessing(false);
    }
  };
  
  const resetProcessor = () => {
    setFile(null);
    setYoutubeUrl('');
    setAnalysis(null);
    setIsProcessing(false);
  };
  
  const handleSelectMeeting = (meeting: any) => {
    let analysisData = meeting.analysis;
    if (typeof analysisData === 'string') {
      try {
        analysisData = JSON.parse(analysisData);
      } catch (e) {
        console.error('Failed to parse analysis:', e);
        analysisData = null;
      }
    }
    
    if (analysisData) {
      setAnalysis({
        title: meeting.title,
        summary: analysisData.summary || '',
        keyDecisions: analysisData.keyDecisions || [],
        publicConcerns: analysisData.publicConcerns || [],
        nextSteps: analysisData.nextSteps || [],
        sentiment: analysisData.sentiment || 'Mixed',
        attendance: analysisData.attendance || 'Not specified',
        mainTopics: analysisData.mainTopics || [],
        processingTime: 'Previously processed',
        summary_markdown: analysisData.summary_markdown,
        summary_data: analysisData.summary_data,
        cb_number: meeting.cb_number,
        url: meeting.url
      });
      setCurrentView('analyzer');
    } else {
        alert("No analysis data found for this meeting.");
    }
  };
  
  const handleDrag = (e: React.DragEvent) => { e.preventDefault(); e.stopPropagation(); if (e.type === "dragenter" || e.type === "dragover") setDragActive(true); else if (e.type === "dragleave") setDragActive(false); };
  const handleDrop = (e: React.DragEvent) => { e.preventDefault(); e.stopPropagation(); setDragActive(false); if (e.dataTransfer.files && e.dataTransfer.files[0]) setFile(e.dataTransfer.files[0]); };
  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => { if (e.target.files && e.target.files[0]) setFile(e.target.files[0]); };

  if (analysis) {
    return (
        <div style={{ minHeight: '100vh', background: '#f7fafc' }}>
            <Navbar onBoardSelect={handleBoardSelect} currentView={currentView} />
            <div className="app-container" style={{ marginTop: 0, background: '#f7fafc' }}>
                <div className="max-width-container">
                    <h1 style={{fontSize: '2rem', fontWeight: '700'}}>{analysis.title}</h1>
                    
                    {analysis.url && (
                        <a href={analysis.url} target="_blank" rel="noopener noreferrer" className="btn btn-secondary" style={{marginBottom: '1.5rem', background: 'white'}}>
                            <Youtube size={16} />
                            Watch on YouTube
                        </a>
                    )}

                    {analysis.summary_data ? (
                        <SummaryRender 
                            summaryData={analysis.summary_data}
                            title={analysis.title}
                            cbNumber={analysis.cb_number}
                        />
                    ) : (
                        <MarkdownRenderer 
                            markdown={analysis.summary_markdown || "No summary available."} 
                        />
                    )}
                    
                    <div style={{ marginTop: '2rem', display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
                        <button onClick={() => {
                            setAnalysis(null);
                            setCurrentView('analyzer');
                            setSelectedCB(null);
                        }} className="btn btn-primary">
                            <ArrowLeft size={16} /> Process Another Meeting
                        </button>

                        {analysis.cb_number && (
                            <button onClick={() => {
                                setAnalysis(null);
                                setCurrentView('meetings');
                                // selectedCB is already set, so this will return to the correct list
                            }} className="btn btn-secondary" style={{background: 'white'}}>
                                Back to CB{analysis.cb_number} Meetings
                            </button>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
  }

  if (currentView === 'meetings' && selectedCB) {
    return (
      <div style={{ minHeight: '100vh', background: '#f7fafc' }}>
        <Navbar onBoardSelect={handleBoardSelect} currentView={currentView} />
        <div className="max-width-container"> 
          <MeetingList cbNumber={selectedCB} onSelectMeeting={handleSelectMeeting} />
          </div>
      </div>
    );
  }

  return (
    <div style={{ minHeight: '100vh', background: '#f7fafc' }}>
      <Navbar onBoardSelect={handleBoardSelect} currentView={currentView} />
      <div className="app-container" style={{ marginTop: 0, background: '#f7fafc' }}>
        <div className="max-width-container">
            <h1 className="flex align-center justify-center gap-3" style={{
              fontSize: '2.5rem', 
              fontWeight: '700', 
              color: '#1a202c', 
              marginBottom: '1rem',
              textAlign: 'center'
            }}>
              CB Meetings Analyzer
            </h1>
            <p style={{textAlign: 'center', color: '#718096', fontSize: '1.2rem', marginBottom: '1rem'}}>
              AI-powered analysis of Community Board meetings
            </p>
            <div className="card">
                <div className="mode-selector" style={{marginBottom: '1rem'}}>
                    <button onClick={() => setProcessingMode('youtube')} className={`mode-button ${processingMode === 'youtube' ? 'active' : ''}`}>YouTube URL</button>
                    <button onClick={() => setProcessingMode('file')} className={`mode-button ${processingMode === 'file' ? 'active' : ''}`}>Upload File</button>
                </div>
                {processingMode === 'youtube' ? (
                    <input type="url" placeholder="https://www.youtube.com/watch?v=..." value={youtubeUrl} onChange={(e) => setYoutubeUrl(e.target.value)} className="input" />
                ) : (
                    <div className={`upload-area ${dragActive ? 'active' : ''}`} onDragEnter={handleDrag} onDragLeave={handleDrag} onDragOver={handleDrag} onDrop={handleDrop} onClick={() => fileInputRef.current?.click()}>
                        <input ref={fileInputRef} type="file" accept="video/*,audio/*" onChange={handleFileSelect} style={{display: 'none'}} />
                        {file ? <div>{file.name}</div> : <div>Drop file or click to browse</div>}
                    </div>
                )}
                <button onClick={processVideo} disabled={(!file && !youtubeUrl) || isProcessing} className="btn btn-success" style={{width: '100%', marginTop: '1rem'}}>
                    {isProcessing ? <><Loader size={20} className="animate-spin" /> Processing...</> : <><Brain size={20} /> Start Analysis</>}
                </button>
            </div>
        </div>
      </div>
    </div>
  );
};

export default App;
