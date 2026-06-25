import api from './api';

// ─── Types ────────────────────────────────────────────────────────────────────
export interface ChatSession {
  id: string;
  title?: string;
  meeting_id?: string;
  created_at: string;
  updated_at: string;
}

export interface ChatMessage {
  id: string;
  session_id: string;
  role: 'user' | 'assistant';
  content: string;
  citations?: Array<{ meeting_id: string; text: string; speaker_name: string; start_ms: number }>;
  created_at: string;
}

// ─── Regular API calls ────────────────────────────────────────────────────────
export const chatApi = {
  listSessions: () =>
    api.get<ChatSession[]>('/chat/sessions').then(r => r.data),

  getSession: (sessionId: string) =>
    api.get<{ session: ChatSession; messages: ChatMessage[] }>(`/chat/sessions/${sessionId}`).then(r => r.data),

  deleteSession: (sessionId: string) =>
    api.delete(`/chat/sessions/${sessionId}`).then(r => r.data),
};

// ─── SSE Streaming chat ───────────────────────────────────────────────────────
export interface StreamChatOptions {
  message: string;
  sessionId?: string;
  meetingId?: string;
  onChunk: (chunk: string) => void;
  onDone: (finalMessage: ChatMessage, sessionId: string) => void;
  onError: (error: string) => void;
}

export async function streamChat(opts: StreamChatOptions): Promise<void> {
  const token = localStorage.getItem('zapper_token');
  const baseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';

  const response = await fetch(`${baseUrl}/api/v1/chat/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({
      message: opts.message,
      session_id: opts.sessionId,
      meeting_id: opts.meetingId,
    }),
  });

  if (!response.ok) {
    const errText = await response.text();
    opts.onError(errText || `HTTP ${response.status}`);
    return;
  }

  const reader = response.body?.getReader();
  if (!reader) {
    opts.onError('No response body');
    return;
  }

  const decoder = new TextDecoder();
  let buffer = '';
  let finalSessionId = opts.sessionId || '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      const data = line.slice(6).trim();
      if (!data || data === '[DONE]') continue;

      try {
        const parsed = JSON.parse(data);
        if (parsed.type === 'chunk' && parsed.content) {
          opts.onChunk(parsed.content);
        } else if (parsed.type === 'done' && parsed.message) {
          if (parsed.session_id) finalSessionId = parsed.session_id;
          opts.onDone(parsed.message, finalSessionId);
        } else if (parsed.type === 'error') {
          opts.onError(parsed.error || 'Unknown error');
        }
      } catch {
        // raw text chunk (non-JSON stream)
        opts.onChunk(data);
      }
    }
  }
}

export default chatApi;
