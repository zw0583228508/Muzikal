import { WebSocketServer, WebSocket } from "ws";
import type { IncomingMessage, Server } from "http";

let wss: WebSocketServer | null = null;

const jobSubs = new Map<string, Set<WebSocket>>();
const projectSubs = new Map<number, Set<WebSocket>>();

export function initWebSocket(server: Server) {
  wss = new WebSocketServer({ server, path: "/api/ws" });

  wss.on("connection", (ws: WebSocket, _req: IncomingMessage) => {
    ws.on("message", (raw) => {
      try {
        const msg = JSON.parse(raw.toString());
        if (msg.type === "subscribe_job" && msg.jobId) {
          if (!jobSubs.has(msg.jobId)) jobSubs.set(msg.jobId, new Set());
          jobSubs.get(msg.jobId)!.add(ws);
        }
        if (msg.type === "subscribe_project" && msg.projectId) {
          const pid = Number(msg.projectId);
          if (!projectSubs.has(pid)) projectSubs.set(pid, new Set());
          projectSubs.get(pid)!.add(ws);
        }
      } catch { /* ignore malformed */ }
    });

    ws.on("close", () => {
      for (const clients of jobSubs.values()) clients.delete(ws);
      for (const clients of projectSubs.values()) clients.delete(ws);
    });

    ws.send(JSON.stringify({ type: "connected" }));
  });
}

export function broadcastJobUpdate(
  jobId: string,
  projectId: number,
  update: Record<string, unknown>,
) {
  const payload = JSON.stringify({ type: "job_update", jobId, projectId, ...update });

  const send = (ws: WebSocket) => {
    if (ws.readyState === WebSocket.OPEN) ws.send(payload);
  };

  jobSubs.get(jobId)?.forEach(send);
  projectSubs.get(projectId)?.forEach(send);
}
