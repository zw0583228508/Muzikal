import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, WifiOff } from "lucide-react";

interface HealthData {
  status: string;
  mockMode: boolean;
  pythonBackend: "ok" | "mock" | "degraded" | "unreachable" | "unknown";
  pythonLatencyMs: number | null;
  uptime: number;
  timestamp: string;
}

export function SystemHealth() {
  const { data } = useQuery<HealthData>({
    queryKey: ["healthz"],
    queryFn: () => fetch("/api/healthz").then((r) => r.json()),
    refetchInterval: 30_000,
    staleTime: 25_000,
  });

  if (!data) return null;

  const isMock = data.mockMode === true;
  const pyOk = data.pythonBackend === "ok" || data.pythonBackend === "mock";
  const pyFailed = data.pythonBackend === "unreachable" || data.pythonBackend === "degraded";

  if (pyOk && !isMock) return null;

  if (pyFailed) {
    return (
      <div className="flex items-center gap-1.5 px-3 py-1 bg-red-500/15 border-b border-red-500/30 text-red-400 text-xs font-medium">
        <WifiOff className="w-3 h-3" />
        Python Backend לא זמין — ניתוח אודיו לא יפעל
      </div>
    );
  }

  if (isMock) {
    return (
      <div className="flex items-center gap-1.5 px-3 py-1 bg-amber-500/15 border-b border-amber-500/30 text-amber-400 text-xs font-medium">
        <AlertTriangle className="w-3 h-3" />
        MOCK MODE פעיל — תוצאות מדומות (dev only)
      </div>
    );
  }

  return null;
}
