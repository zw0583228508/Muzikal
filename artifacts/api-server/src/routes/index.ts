import { Router, type IRouter } from "express";
import healthRouter from "./health";
import projectsRouter from "./projects";
import jobsRouter from "./jobs";
import stylesRouter from "./styles";

const router: IRouter = Router();

router.use(healthRouter);
router.use("/projects", projectsRouter);
router.use("/jobs", jobsRouter);
router.use("/styles", stylesRouter);

export default router;
