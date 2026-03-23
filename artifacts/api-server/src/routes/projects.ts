/**
 * Projects router — thin aggregator.
 *
 * Delegates to domain-specific sub-routers:
 *   project-crud.routes        GET|POST /  +  GET|DELETE /:id  +  POST /:id/upload
 *   project-analysis.routes    POST /:id/analyze  +  GET /:id/analysis  +  corrections  +  locks
 *   project-arrangement.routes POST|GET /:id/arrangement  +  history  +  regen section/track
 *   project-files.routes       GET /:id/audio  +  GET /:id/files  +  download  +  serve
 *   project-export.routes      POST /:id/export  +  bundle  +  render
 */

import { Router } from "express";

import crudRouter        from "./project-crud.routes";
import analysisRouter    from "./project-analysis.routes";
import arrangementRouter from "./project-arrangement.routes";
import filesRouter       from "./project-files.routes";
import exportRouter      from "./project-export.routes";

const router = Router();

router.use("/", crudRouter);
router.use("/", analysisRouter);
router.use("/", arrangementRouter);
router.use("/", filesRouter);
router.use("/", exportRouter);

export default router;
