import express, { type Express, type Request, type Response, type NextFunction } from "express";
import cors from "cors";
import cookieParser from "cookie-parser";
import pinoHttp from "pino-http";
import { randomUUID } from "crypto";
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

app.use("/api", router);

export default app;
