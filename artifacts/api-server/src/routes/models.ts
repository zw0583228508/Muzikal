import { Router, type IRouter } from "express";

const router: IRouter = Router();

const PYTHON_BACKEND = process.env.PYTHON_BACKEND_URL || "http://localhost:8001";

// GET /api/models — proxy the full model registry from Python backend
router.get("/", async (_req, res) => {
  try {
    const upstream = await fetch(`${PYTHON_BACKEND}/python-api/models`, {
      headers: { "Content-Type": "application/json" },
    });
    if (!upstream.ok) {
      const err = await upstream.text().catch(() => "");
      res.status(502).json({ error: `Python backend error (${upstream.status}): ${err}` });
      return;
    }
    const data = await upstream.json();
    res.json(data);
  } catch (err) {
    res.status(502).json({ error: "Model registry unavailable — Python backend unreachable" });
  }
});

// GET /api/models/:task — proxy single-task model lookup
router.get("/:task", async (req, res) => {
  const { task } = req.params;
  try {
    const upstream = await fetch(`${PYTHON_BACKEND}/python-api/models/${encodeURIComponent(task)}`, {
      headers: { "Content-Type": "application/json" },
    });
    if (upstream.status === 404) {
      res.status(404).json({ error: `No active model found for task: ${task}` });
      return;
    }
    if (!upstream.ok) {
      const err = await upstream.text().catch(() => "");
      res.status(502).json({ error: `Python backend error (${upstream.status}): ${err}` });
      return;
    }
    const data = await upstream.json();
    res.json(data);
  } catch (err) {
    res.status(502).json({ error: "Model registry unavailable — Python backend unreachable" });
  }
});

export default router;
