import api from './api';

// ─── Types ────────────────────────────────────────────────────────────────────
export interface Meeting {
  id: string;
  title?: string;
  meeting_url?: string;
  platform: 'meet' | 'teams';
  status: 'joining' | 'lobby' | 'recording' | 'processing' | 'done' | 'error' | 'cancelled';
  started_at?: string;
  ended_at?: string;
  duration_seconds?: number;
  participant_names: string[];
  participant_count: number;
  summary_md?: string;
  summary_json?: Record<string, any>;
  health_score?: number;
  engagement_score?: number;
  sentiment?: string;
  zapper_muted: boolean;
  created_at: string;
}

export interface TranscriptSegment {
  id: string;
  speaker_name: string;
  speaker_id?: string;
  start_ms: number;
  end_ms: number;
  text: string;
  confidence?: number;
}

export interface StartBotRequest {
  meeting_url: string;
  title?: string;
  visual_capture_mode?: 'disabled' | 'screenshots' | 'video';
  settings?: Record<string, any>;
}

// ─── API calls ────────────────────────────────────────────────────────────────
export const meetingsApi = {
  list: (params?: { status?: string; limit?: number; offset?: number }) =>
    api.get<Meeting[]>('/meetings', { params }).then(r => r.data),

  get: (id: string) =>
    api.get<Meeting>(`/meetings/${id}`).then(r => r.data),

  startBot: (data: StartBotRequest) =>
    api.post<{ meeting_id: string; slot: number }>('/meetings/start', {
      url: data.meeting_url,
      display_name: data.title,
      visual_capture_mode: data.visual_capture_mode
    }).then(r => r.data),

  stopBot: (id: string) =>
    api.post(`/meetings/${id}/stop`).then(r => r.data),

  mute: (id: string, muted: boolean) =>
    api.patch(`/meetings/${id}/mute`, { muted }).then(r => r.data),

  delete: (id: string) =>
    api.delete(`/meetings/${id}`).then(r => r.data),

  getTranscript: (id: string) =>
    api.get<TranscriptSegment[]>(`/meetings/${id}/transcript`).then(r => r.data),

  getSummary: (id: string) =>
    api.get<{ summary_md: string; summary_json: any }>(`/meetings/${id}/summary`).then(r => r.data),

  regenerateSummary: (id: string) =>
    api.post(`/meetings/${id}/summary/regenerate`).then(r => r.data),

  updateParticipants: (id: string, participant_names: string[]) =>
    api.patch(`/meetings/${id}/participants`, { participant_names }).then(r => r.data),

  getUpcomingCount: () =>
    api.get<{ count: number }>('/meetings/upcoming/count').then(r => r.data),
};

export default meetingsApi;
