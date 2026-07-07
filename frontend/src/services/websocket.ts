import { useCallback, useEffect, useRef } from 'react';
import { useAuthStore } from '../store/authStore';

const WS_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8000';

export type LiveEvent =
  | { type: 'transcript_segment'; segment: { speaker_name: string; text: string; start_ms: number } }
  | { type: 'participant_joined'; name: string }
  | { type: 'participant_left'; name: string }
  | { type: 'status_change'; status: string }
  | { type: 'ping' };

interface UseWebSocketOptions {
  meetingId: string;
  onEvent: (event: LiveEvent) => void;
  enabled?: boolean;
}

export function useWebSocket({ meetingId, onEvent, enabled = true }: UseWebSocketOptions) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const { token } = useAuthStore();

  const onEventRef = useRef(onEvent);
  useEffect(() => {
    onEventRef.current = onEvent;
  }, [onEvent]);

  const connect = useCallback(() => {
    if (!enabled || !meetingId || !token) return;
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const url = `${WS_URL}/ws/meetings/${meetingId}?token=${encodeURIComponent(token)}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log(`[ws] Connected to meeting ${meetingId}`);
    };

    ws.onmessage = (e) => {
      try {
        const evt = JSON.parse(e.data) as LiveEvent;
        onEventRef.current(evt);
      } catch {
        // ignore malformed frames
      }
    };

    ws.onclose = (e) => {
      if (e.code !== 1000) {
        // Reconnect after 3 seconds on unexpected close
        reconnectTimer.current = setTimeout(connect, 3000);
      }
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [meetingId, token, enabled]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      wsRef.current?.close(1000, 'component unmounted');
    };
  }, [connect]);

  const send = useCallback((data: object) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    }
  }, []);

  return { send };
}
