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

/**
 * Subscribes to real-time WebSocket job updates for a project.
 * Falls back gracefully to polling if the WebSocket connection fails
 * (the polling hook remains active regardless).
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

    function connect() {
      ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!alive) { ws.close(); return; }
        ws.send(JSON.stringify({ type: "subscribe_project", projectId }));
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === "job_update") {
            onUpdateRef.current(msg as JobUpdate);
          }
        } catch { /* ignore */ }
      };

      ws.onerror = () => { /* silently fall back to polling */ };

      ws.onclose = () => {
        wsRef.current = null;
        // Reconnect after 3s if still mounted
        if (alive) setTimeout(connect, 3000);
      };
    }

    connect();

    return () => {
      alive = false;
      ws?.close();
      wsRef.current = null;
    };
  }, [projectId]);

  return { subscribeToJob };
}
