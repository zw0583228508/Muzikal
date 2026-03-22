import { Job } from "@workspace/api-client-react";
import { Progress } from "@/components/ui/progress";
import { Loader2, AlertCircle, CheckCircle2, Clock, ChevronDown, ChevronUp } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { useTranslation } from "react-i18next";
import { useState } from "react";
import { cn } from "@/lib/utils";

const STEP_ORDER: Record<string, string[]> = {
  analysis: [
    "preprocessing", "separation", "rhythm", "key", "chords",
    "melody", "vocals", "structure",
  ],
  arrangement: [
    "section_map", "harmonic_plan", "instrumentation", "orchestration", "transitions",
  ],
  export: ["quantization", "midi_export", "musicxml_export", "audio_render"],
  render: ["synthesis", "mixing", "mastering", "output"],
};

function inferStepStatus(stepName: string, currentStep: string, progress: number, jobStatus: string) {
  const normalized = (currentStep || "").toLowerCase();
  const step = stepName.toLowerCase();
  if (normalized.includes(step) || normalized.includes(step.replace("_", " "))) return "running";
  if (jobStatus === "completed") return "completed";
  const order = Object.values(STEP_ORDER).flat();
  const currentIdx = order.findIndex(s => normalized.includes(s));
  const stepIdx = order.indexOf(step);
  if (currentIdx >= 0 && stepIdx < currentIdx) return "completed";
  return "pending";
}

export function JobProgress({ job }: { job: Job | null | undefined }) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  if (!job) return null;

  const isRunning = job.status === "queued" || job.status === "running";
  const isFailed = job.status === "failed";
  const isComplete = job.status === "completed";

  const steps = STEP_ORDER[job.type] ?? [];
  const isMockJob = !!(job as any).isMock;

  return (
    <AnimatePresence>
      {(isRunning || isFailed || isComplete) && (
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -20 }}
          className="fixed top-20 right-6 z-50 w-80 glass-panel p-4 rounded-xl rtl:right-auto rtl:left-6"
        >
          <div className="flex items-center gap-3 mb-3">
            {isRunning && <Loader2 className="w-5 h-5 text-primary animate-spin" />}
            {isFailed && <AlertCircle className="w-5 h-5 text-destructive" />}
            {isComplete && <CheckCircle2 className="w-5 h-5 text-green-400 text-glow" />}

            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <h4 className="text-sm font-semibold capitalize tracking-wider text-white">
                  {t(job.type)} {t("Job")}
                </h4>
                {isMockJob && (
                  <span className="text-[9px] uppercase font-bold px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-400 border border-amber-500/30 tracking-widest flex-shrink-0">
                    MOCK
                  </span>
                )}
              </div>
              <p className="text-xs text-muted-foreground truncate" dir="ltr">
                {t(job.currentStep || job.status)}
              </p>
            </div>
            <div className="flex items-center gap-1">
              <span className="text-xs font-mono font-bold text-primary" dir="ltr">
                {Math.round(job.progress)}%
              </span>
              {steps.length > 0 && (
                <button
                  onClick={() => setExpanded(e => !e)}
                  className="text-muted-foreground hover:text-white transition-colors ml-1"
                  title={expanded ? t("Hide steps") : t("Show steps")}
                >
                  {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                </button>
              )}
            </div>
          </div>

          <Progress
            value={job.progress}
            indicatorColor={isFailed ? "bg-destructive" : isComplete ? "bg-green-400" : "bg-primary"}
            className="ltr:origin-left rtl:origin-right"
          />

          <AnimatePresence>
            {expanded && steps.length > 0 && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                className="mt-3 space-y-1 overflow-hidden"
              >
                {steps.map((step) => {
                  const status = inferStepStatus(step, job.currentStep ?? "", job.progress, job.status);
                  return (
                    <div key={step} className="flex items-center gap-2 text-xs">
                      <span className={cn("w-2 h-2 rounded-full flex-shrink-0",
                        status === "completed" ? "bg-green-400" :
                        status === "running" ? "bg-primary animate-pulse" :
                        "bg-white/15"
                      )} />
                      <span className={cn("flex-1 capitalize",
                        status === "running" ? "text-white" :
                        status === "completed" ? "text-green-400/80" :
                        "text-muted-foreground"
                      )}>
                        {t(step.replace(/_/g, " "))}
                      </span>
                      {status === "running" && <Loader2 className="w-3 h-3 text-primary animate-spin" />}
                      {status === "completed" && <CheckCircle2 className="w-3 h-3 text-green-400/70" />}
                      {status === "pending" && <Clock className="w-3 h-3 text-white/20" />}
                    </div>
                  );
                })}
              </motion.div>
            )}
          </AnimatePresence>

          {isFailed && (
            <p className="text-xs text-destructive mt-2 bg-destructive/10 p-2 rounded border border-destructive/20">
              {t(job.errorMessage || "An unknown error occurred")}
            </p>
          )}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
