import React from 'react';

interface MarkdownRendererProps {
  markdown: string;
}

const MarkdownRenderer: React.FC<MarkdownRendererProps> = ({ markdown }) => {
  // Simple markdown to HTML conversion
  const renderMarkdown = (text: string): string => {
    if (!text) return '';
    
    let processedText = text;
    
    // Convert headers
    processedText = processedText.replace(/^### (.*$)/gim, '<h3>$1</h3>');
    processedText = processedText.replace(/^## (.*$)/gim, '<h2>$1</h2>');
    processedText = processedText.replace(/^# (.*$)/gim, '<h1>$1</h1>');
    
    // Convert bold
    processedText = processedText.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    
    // Convert lists
    processedText = processedText.replace(/^\* (.+)$/gim, '<li>$1</li>');
    processedText = processedText.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>');
    
    // Convert line breaks
    processedText = processedText.replace(/\n\n/g, '</p><p>');
    processedText = '<p>' + processedText + '</p>';
    
    // Clean up empty paragraphs
    processedText = processedText.replace(/<p><\/p>/g, '');
    processedText = processedText.replace(/<p>(<h[1-3]>)/g, '$1');
    processedText = processedText.replace(/(<\/h[1-3]>)<\/p>/g, '$1');
    
    return processedText;
  };

  const styles = {
    container: {
      background: 'white',
      borderRadius: '1rem',
      padding: '2rem',
      boxShadow: '0 1px 3px rgba(0, 0, 0, 0.1)',
      lineHeight: 1.6,
      color: '#2d3748'
    }
  };

  return (
    <div style={styles.container}>
      <div 
        className="markdown-content"
        dangerouslySetInnerHTML={{ __html: renderMarkdown(markdown) }}
      />
      <style>{`
        .markdown-content h1 {
          font-size: 2rem;
          font-weight: 700;
          margin-bottom: 1rem;
          margin-top: 1rem;
          color: #1a202c;
        }
        .markdown-content h2 {
          font-size: 1.5rem;
          font-weight: 600;
          margin-bottom: 0.75rem;
          margin-top: 1.5rem;
          color: #2d3748;
        }
        .markdown-content h3 {
          font-size: 1.25rem;
          font-weight: 600;
          margin-bottom: 0.5rem;
          margin-top: 1rem;
          color: #4a5568;
        }
        .markdown-content p {
          margin-bottom: 1rem;
          font-size: 1rem;
          line-height: 1.6;
        }
        .markdown-content ul {
          margin-bottom: 1rem;
          padding-left: 1.5rem;
        }
        .markdown-content li {
          margin-bottom: 0.5rem;
          list-style-type: disc;
        }
        .markdown-content strong {
          font-weight: 600;
          color: #1a202c;
        }
      `}</style>
    </div>
  );
};

export default MarkdownRenderer;