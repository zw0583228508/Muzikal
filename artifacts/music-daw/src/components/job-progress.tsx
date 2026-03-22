import { Job } from "@workspace/api-client-react";
import { Progress } from "@/components/ui/progress";
import { Loader2, AlertCircle, CheckCircle2 } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

export function JobProgress({ job }: { job: Job | null | undefined }) {
  if (!job) return null;

  const isRunning = job.status === "queued" || job.status === "running";
  const isFailed = job.status === "failed";
  const isComplete = job.status === "completed";

  return (
    <AnimatePresence>
      {(isRunning || isFailed || isComplete) && (
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -20 }}
          className="fixed top-20 right-6 z-50 w-80 glass-panel p-4 rounded-xl"
        >
          <div className="flex items-center gap-3 mb-3">
            {isRunning && <Loader2 className="w-5 h-5 text-primary animate-spin" />}
            {isFailed && <AlertCircle className="w-5 h-5 text-destructive" />}
            {isComplete && <CheckCircle2 className="w-5 h-5 text-green-400 text-glow" />}
            
            <div className="flex-1">
              <h4 className="text-sm font-semibold capitalize tracking-wider text-white">
                {job.type} Job
              </h4>
              <p className="text-xs text-muted-foreground truncate">
                {job.currentStep || job.status}
              </p>
            </div>
            <span className="text-xs font-mono font-bold text-primary">
              {Math.round(job.progress)}%
            </span>
          </div>
          
          <Progress 
            value={job.progress} 
            indicatorColor={isFailed ? "bg-destructive" : isComplete ? "bg-green-400" : "bg-primary"} 
          />
          
          {isFailed && (
            <p className="text-xs text-destructive mt-2 bg-destructive/10 p-2 rounded border border-destructive/20">
              {job.errorMessage || "An unknown error occurred"}
            </p>
          )}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
