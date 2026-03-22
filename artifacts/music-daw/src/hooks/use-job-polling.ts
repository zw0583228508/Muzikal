import { useState, useEffect } from "react";
import { useGetJobStatus } from "@workspace/api-client-react";

export function useJobPolling(jobId: string | null, onComplete?: () => void) {
  const [isPolling, setIsPolling] = useState(false);

  useEffect(() => {
    if (jobId) {
      setIsPolling(true);
    } else {
      setIsPolling(false);
    }
  }, [jobId]);

  const { data: job, error } = useGetJobStatus(jobId || "", {
    query: {
      enabled: isPolling && !!jobId,
      refetchInterval: (query) => {
        const currentJob = query.state.data;
        if (!currentJob) return 1000;
        if (currentJob.status === "completed" || currentJob.status === "failed") {
          return false;
        }
        return 1000; // poll every second
      },
    }
  });

  useEffect(() => {
    if (job && job.status === "completed") {
      setIsPolling(false);
      onComplete?.();
    }
    if (job && job.status === "failed") {
      setIsPolling(false);
    }
  }, [job?.status, onComplete]);

  return { job, isPolling, error };
}
