import { useTranslation } from "react-i18next";
import { AlertTriangle, XCircle } from "lucide-react";

interface MockBannerProps {
  onDismiss: () => void;
}

export function MockBanner({ onDismiss }: MockBannerProps) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-3 px-4 py-2 bg-amber-500/15 border-b border-amber-500/30 text-amber-400 text-xs">
      <AlertTriangle className="w-4 h-4 flex-shrink-0" />
      <span className="flex-1">
        <strong>{t("MOCK MODE")}</strong> —{" "}
        {t("Python audio backend unavailable. Results are simulated for UI testing only and do not reflect real analysis.")}
      </span>
      <button onClick={onDismiss} className="text-amber-400/60 hover:text-amber-400 ml-2">
        <XCircle className="w-4 h-4" />
      </button>
    </div>
  );
}

interface FailedBannerProps {
  message: string;
}

export function FailedBanner({ message }: FailedBannerProps) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-3 px-4 py-2 bg-red-500/15 border-b border-red-500/30 text-red-400 text-xs">
      <XCircle className="w-4 h-4 flex-shrink-0" />
      <span>
        <strong>{t("Job Failed")}</strong> — {message}
      </span>
    </div>
  );
}
