import express, { type Express, type Request, type Response, type NextFunction } from "express";
import cors from "cors";
import cookieParser from "cookie-parser";
import pinoHttp from "pino-http";
import { randomUUID } from "crypto";
import rateLimit from "express-rate-limit";
import router from "./routes";
import { logger } from "./lib/logger";
import { authMiddleware } from "./middlewares/authMiddleware";

const app: Express = express();

// ── Correlation ID middleware ─────────────────────────────────────────────────
// Propagates or generates an x-correlation-id header for every request.
// All downstream log calls include this ID for distributed tracing.
app.use((req: Request, res: Response, next: NextFunction) => {
  const id = (req.headers["x-correlation-id"] as string) || randomUUID();
  (req as any).correlationId = id;
  res.setHeader("x-correlation-id", id);
  next();
});

app.use(
  pinoHttp({
    logger,
    genReqId: (req) => (req as any).correlationId || randomUUID(),
    serializers: {
      req(req) {
        return {
          id: req.id,
          correlationId: (req.raw as any).correlationId,
          method: req.method,
          url: req.url?.split("?")[0],
        };
      },
      res(res) {
        return {
          statusCode: res.statusCode,
        };
      },
    },
  }),
);

app.use(cors({ credentials: true, origin: true }));
app.use(cookieParser());
app.use(express.json());
app.use(express.urlencoded({ extended: true }));
app.use(authMiddleware);

// ── Rate Limiting ─────────────────────────────────────────────────────────────
// General API guard: 200 requests per 15 minutes per IP
const generalLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  max: 200,
  standardHeaders: true,
  legacyHeaders: false,
  message: { error: "Too many requests — please try again later" },
  handler(req, res, _next, options) {
    logger.warn({ ip: req.ip, url: req.url }, "Rate limit exceeded (general)");
    res.status(429).json(options.message);
  },
});

// Heavy ML endpoints: 10 requests per minute per IP (analysis jobs)
const analyzeLimiter = rateLimit({
  windowMs: 60 * 1000,
  max: 10,
  standardHeaders: true,
  legacyHeaders: false,
  message: { error: "Analysis rate limit exceeded — maximum 10 requests per minute" },
  handler(req, res, _next, options) {
    logger.warn({ ip: req.ip, url: req.url }, "Rate limit exceeded (analyze)");
    res.status(429).json(options.message);
  },
});

// Render jobs: 5 requests per minute per IP (audio rendering is expensive)
const renderLimiter = rateLimit({
  windowMs: 60 * 1000,
  max: 5,
  standardHeaders: true,
  legacyHeaders: false,
  message: { error: "Render rate limit exceeded — maximum 5 requests per minute" },
  handler(req, res, _next, options) {
    logger.warn({ ip: req.ip, url: req.url }, "Rate limit exceeded (render)");
    res.status(429).json(options.message);
  },
});

app.use("/api", generalLimiter);
app.use(/^\/api\/projects\/\d+\/analyze$/, analyzeLimiter);
app.use(/^\/api\/projects\/\d+\/render$/, renderLimiter);

app.use("/api", router);

export default app;
