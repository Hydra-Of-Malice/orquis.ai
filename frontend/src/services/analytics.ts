import api from './api';

// ─── Types ────────────────────────────────────────────────────────────────────
export interface OverviewStats {
  total_meetings: number;
  meetings_this_week: number;
  hours_saved: number;
  action_item_completion_rate: number;
  total_action_items: number;
  avg_health_score: number;
  avg_meeting_duration_mins: number;
  recent_insights?: any[];
  // Legacy fields to prevent typescript errors elsewhere
  total_meetings_delta?: number;
  total_hours?: number;
  total_hours_delta?: number;
  avg_health_delta?: number;
  action_items_completed?: number;
  action_items_total?: number;
}

export interface SentimentPoint {
  name: string;
  value: number;
}

export interface SpeakerTalkTime {
  name: string;
  value: number;  // minutes
}

export interface TeamMember {
  user_id: string;
  display_name: string;
  avatar_url?: string;
  avg_health: number;
  hours_spoken: number;
  tasks_synced: number;
  action_item_resolution: number;
}

export interface CoachingScore {
  user_id: string;
  week_start: string;
  talk_ratio: number;
  questions_asked: number;
  action_items_completed: number;
  meetings_attended: number;
  engagement_avg: number;
}

export interface HeatmapCell {
  day: number;     // 0 = Monday … 6 = Sunday
  hour: number;    // 0–23
  value: number;   // meeting load count
}

// ─── API calls ────────────────────────────────────────────────────────────────
export const analyticsApi = {
  getOverview: (params?: { days?: number }) =>
    api.get<OverviewStats>('/analytics/overview', { params }).then(r => r.data),

  getSentimentTrend: (params?: { days?: number }) =>
    api.get<SentimentPoint[]>('/analytics/sentiment-trend', { params }).then(r => r.data),

  getDepartmentHours: () =>
    api.get<SpeakerTalkTime[]>('/analytics/department-hours').then(r => r.data),

  getTeamMembers: () =>
    api.get<any>('/analytics/team').then(r => r.data),

  getCoachingScores: (params?: { weeks?: number }) =>
    api.get<CoachingScore[]>('/analytics/coaching', { params }).then(r => r.data),

  getHeatmap: (params?: { weeks?: number }) =>
    api.get<HeatmapCell[]>('/analytics/heatmap', { params }).then(r => r.data),

  getInsights: () =>
    api.get<{ insights: string[] }>('/analytics/insights').then(r => r.data),
};

export default analyticsApi;
