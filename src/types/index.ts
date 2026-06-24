export interface Organization {
  id: string;
  name: string;
  slug: string;
  plan: "free" | "pro" | "enterprise";
  settings: Record<string, any>;
  createdAt: string;
}

export interface User {
  id: string;
  orgId: string;
  email: string;
  name: string;
  role: "super_admin" | "org_admin" | "team_lead" | "member" | "guest";
  avatarUrl?: string;
  preferences: Record<string, any>;
  createdAt: string;
}

export interface Meeting {
  id: string;
  orgId: string;
  title: string;
  meetingType: "zoom" | "teams" | "meet" | "webex" | "uploaded";
  externalMeetingId?: string;
  startedAt: string;
  endedAt?: string;
  durationSeconds: number;
  status: "scheduled" | "live" | "processing" | "completed" | "failed";
  recordingUrl?: string;
  audioUrl?: string;
  botJoinUrl?: string;
  metadata?: Record<string, any>;
  createdBy: string;
  healthScore?: number;
}

export interface Participant {
  id: string;
  meetingId: string;
  userId?: string;
  name: string;
  email?: string;
  role: "host" | "attendee";
  talkTimeSeconds: number;
  joinedAt: string;
  leftAt?: string;
}

export interface TranscriptSegment {
  id: string;
  meetingId: string;
  speakerId: string;
  speakerName: string;
  text: string;
  startMs: number;
  endMs: number;
  confidence: number;
  language: string;
  createdAt: string;
  highlighted?: boolean;
}

export interface Summary {
  id: string;
  meetingId: string;
  summaryType: "executive" | "technical" | "sales" | "recruiter" | "custom";
  content: {
    tldr: string;
    decisions: string[];
    actionItems: string[];
    risks: string[];
    questions: string[];
    topics: string[];
  };
  modelUsed: string;
  tokensUsed: number;
  createdAt: string;
}

export interface ActionItem {
  id: string;
  meetingId: string;
  assigneeId?: string;
  assigneeName: string;
  title: string;
  description?: string;
  dueDate?: string;
  priority: "low" | "medium" | "high" | "urgent";
  status: "pending" | "in_progress" | "done" | "cancelled";
  dependencies?: string[];
  riskLevel?: "low" | "medium" | "high";
  sourceSegmentId?: string;
  externalTaskId?: string;
  createdAt: string;
}

export interface Decision {
  id: string;
  meetingId: string;
  title: string;
  description?: string;
  decisionMakers: string[];
  alternativesDiscussed?: string;
  risks?: string;
  nextSteps?: string;
  sourceSegmentId?: string;
  createdAt: string;
}

export interface Question {
  id: string;
  meetingId: string;
  askerId: string;
  askerName: string;
  text: string;
  answered: boolean;
  answer?: string;
  sourceSegmentId?: string;
}

export interface MeetingAnalytics {
  id: string;
  meetingId: string;
  engagementScore: number;
  participationScore: number;
  speakingBalanceScore: number;
  sentimentScore: number;
  focusScore: number;
  interruptionsCount: number;
  questionsCount: number;
  decisionsCount: number;
  actionItemsCount: number;
  meetingHealthScore: number;
  perSpeakerStats: Record<string, {
    talkTimeSeconds: number;
    percentage: number;
    wpm: number;
    questionsCount: number;
    interruptionsCount: number;
  }>;
  timelineData: {
    minute: number;
    engagement: number;
    sentiment: number; // -1 to 1
  }[];
  computedAt: string;
}

export interface Project {
  id: string;
  orgId: string;
  name: string;
  description: string;
  color: string;
  icon: string;
  ownerId: string;
  createdAt: string;
  meetingsCount: number;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  citations?: {
    meetingId: string;
    meetingTitle: string;
    timestamp: string;
    speaker: string;
    snippet: string;
  }[];
  suggestedQuestions?: string[];
}

export interface ChatConversation {
  id: string;
  title: string;
  createdAt: string;
  messages: ChatMessage[];
}

export interface AutomationRule {
  id: string;
  orgId: string;
  name: string;
  trigger: string;
  conditions: Record<string, any>;
  actions: {
    type: string;
    config: Record<string, any>;
  }[];
  isActive: boolean;
  createdBy: string;
  createdAt: string;
}

export interface Integration {
  id: string;
  orgId: string;
  provider: string;
  status: "connected" | "disconnected" | "error";
  config?: Record<string, any>;
  lastSync?: string;
}
