import { useEffect, useRef, useCallback } from "react";

export type JobUpdate = {
  type: "job_update";
  jobId: string;
  projectId: number;
  status: string;
  progress: number;
  currentStep: string;
  isMock?: boolean;
  errorMessage?: string | null;
};

type Options = {
  projectId: number | null;
  onJobUpdate: (update: JobUpdate) => void;
};

const MAX_RETRIES = 5;
const BACKOFF_BASE = 1000;

/**
 * Subscribes to real-time WebSocket job updates for a project.
 * Uses exponential backoff (1s, 2s, 4s, 8s, 16s) then gives up and
 * falls back entirely to the polling hook (which is always active).
 */
export function useJobWebSocket({ projectId, onJobUpdate }: Options) {
  const wsRef = useRef<WebSocket | null>(null);
  const onUpdateRef = useRef(onJobUpdate);
  onUpdateRef.current = onJobUpdate;

  const subscribeToJob = useCallback((jobId: string) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "subscribe_job", jobId }));
    }
  }, []);

  useEffect(() => {
    if (!projectId) return;

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/api/ws`;

    let ws: WebSocket;
    let alive = true;
    let retryCount = 0;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;

    function connect() {
      if (!alive) return;
      ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!alive) { ws.close(); return; }
        retryCount = 0; // reset on successful connection
        ws.send(JSON.stringify({ type: "subscribe_project", projectId }));
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === "job_update") {
            onUpdateRef.current(msg as JobUpdate);
          }
        } catch { /* ignore malformed messages */ }
      };

      ws.onerror = () => { /* silently fall back to polling */ };

      ws.onclose = () => {
        wsRef.current = null;
        if (!alive) return;

        if (retryCount >= MAX_RETRIES) {
          console.warn(
            `[WebSocket] Max retries (${MAX_RETRIES}) reached — using polling fallback only`
          );
          return;
        }

        const delay = BACKOFF_BASE * Math.pow(2, retryCount);
        retryCount++;
        console.info(`[WebSocket] Reconnecting in ${delay}ms (attempt ${retryCount}/${MAX_RETRIES})`);
        retryTimer = setTimeout(connect, delay);
      };
    }

    connect();

    return () => {
      alive = false;
      if (retryTimer) clearTimeout(retryTimer);
      ws?.close();
      wsRef.current = null;
    };
  }, [projectId]);

  return { subscribeToJob };
}
