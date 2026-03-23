import { Router, type IRouter, type Request, type Response } from "express";
import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const router: IRouter = Router();

const PYTHON_BACKEND = `http://localhost:${process.env.PYTHON_BACKEND_PORT ?? 8001}`;

async function proxyToPython(
  path: string,
  method: "GET" | "POST" | "DELETE",
  body?: unknown,
): Promise<{ status: number; data: unknown }> {
  const url = `${PYTHON_BACKEND}${path}`;
  const opts: RequestInit = {
    method,
    headers: { "Content-Type": "application/json" },
    ...(body ? { body: JSON.stringify(body) } : {}),
  };
  const res = await fetch(url, opts);
  const data = await res.json().catch(() => ({}));
  return { status: res.status, data };
}

// POST /api/agent/chat
// Body: { message: string, projectId?: string, sessionId?: string }
router.post("/chat", async (req: Request, res: Response) => {
  const { message, projectId, sessionId } = req.body ?? {};
  if (!message) {
    return res.status(400).json({ error: "message is required" });
  }
  try {
    const { status, data } = await proxyToPython("/agent/chat", "POST", {
      message,
      project_id: projectId,
      session_id: sessionId,
    });
    return res.status(status).json(data);
  } catch (err) {
    return res.status(502).json({ error: "Python backend unavailable", detail: String(err) });
  }
});

// GET /api/agent/session/:id
router.get("/session/:id", async (req: Request, res: Response) => {
  const { id } = req.params;
  try {
    const { status, data } = await proxyToPython(`/agent/session/${id}`, "GET");
    return res.status(status).json(data);
  } catch (err) {
    return res.status(502).json({ error: "Python backend unavailable" });
  }
});

// POST /api/agent/confirm
// Body: { sessionId: string, projectId?: string }
router.post("/confirm", async (req: Request, res: Response) => {
  const { sessionId, projectId } = req.body ?? {};
  if (!sessionId) {
    return res.status(400).json({ error: "sessionId is required" });
  }
  try {
    const { status, data } = await proxyToPython("/agent/confirm", "POST", {
      session_id: sessionId,
      project_id: projectId,
    });
    return res.status(status).json(data);
  } catch (err) {
    return res.status(502).json({ error: "Python backend unavailable" });
  }
});

// POST /api/agent/enrich
// Body: { genre, era, region, analysisData? }
router.post("/enrich", async (req: Request, res: Response) => {
  try {
    const { status, data } = await proxyToPython("/agent/enrich", "POST", req.body);
    return res.status(status).json(data);
  } catch (err) {
    return res.status(502).json({ error: "Python backend unavailable" });
  }
});

export default router;
