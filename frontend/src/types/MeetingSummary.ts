export interface ActionItem {
    task: string;
    owner: string;
    due: string;
  }
  
  export interface Decision {
    item: string;
    outcome: string;
    vote?: string;
    details: string;
  }
  
  export interface Topic {
    title: string;
    speakers: string[];
    summary: string;
    decisions: string[];
    detailed_decisions?: Decision[];
    action_items: ActionItem[];
    sentiment: 'positive' | 'neutral' | 'negative';
    key_points?: string[];
    concerns_raised?: string[];
    proposals?: string[];
  }
  
  export interface MeetingSummaryData {
    meeting_date: string;
    meeting_type: string;
    executive_summary: string;
    topics: Topic[];
    overall_sentiment: 'positive' | 'neutral' | 'negative';
    attendance: Record<string, number>;
    key_decisions: Decision[];
    public_concerns: string[];
    next_steps: string[];
    total_decisions: number;
    total_action_items: number;
    primary_focus?: string;
  }
  
  export interface MeetingAnalysis {
    title: string;
    summary: string; // This is now the executive_summary
    keyDecisions: Decision[];
    publicConcerns: string[];
    nextSteps: string[];
    sentiment: string;
    attendance: string;
    mainTopics: string[];
    processingTime: string;
    summary_markdown?: string;
    summary_json?: MeetingSummaryData; // Add this
    cb_number?: number;
    url?: string;
  }