import { Router, type IRouter } from "express";
import healthRouter from "./health";
import authRouter from "./auth";
import projectsRouter from "./projects";
import jobsRouter from "./jobs";
import stylesRouter from "./styles";
import agentRouter from "./agent";

const router: IRouter = Router();

router.use(healthRouter);
router.use(authRouter);
router.use("/projects", projectsRouter);
router.use("/jobs", jobsRouter);
router.use("/styles", stylesRouter);
router.use("/agent", agentRouter);

export default router;
