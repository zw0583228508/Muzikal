import { Router, type IRouter } from "express";
import { logger } from "../lib/logger";

const router: IRouter = Router();

router.get("/healthz", async (_req, res) => {
  const mockMode = process.env.MOCK_MODE === "true";
  let pythonStatus = "unknown";
  let pythonLatencyMs: number | null = null;

  if (!mockMode) {
    const t0 = Date.now();
    try {
      const resp = await fetch("http://localhost:8001/python-api/health", {
        signal: AbortSignal.timeout(3000),
      });
      pythonStatus = resp.ok ? "ok" : "degraded";
      pythonLatencyMs = Date.now() - t0;
    } catch {
      pythonStatus = "unreachable";
      logger.warn("Python backend health check failed");
    }
  } else {
    pythonStatus = "mock";
  }

  res.json({
    status: "ok",
    mockMode,
    pythonBackend: pythonStatus,
    pythonLatencyMs,
    uptime: Math.floor(process.uptime()),
    timestamp: new Date().toISOString(),
  });
});

export default router;
