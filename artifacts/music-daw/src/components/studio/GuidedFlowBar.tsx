import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import { Upload, Zap, Layers, Download, ChevronLeft } from "lucide-react";

type FlowStep = "upload" | "analyze" | "arrange" | "export";

interface GuidedFlowBarProps {
  hasAudio: boolean;
  hasAnalysis: boolean;
  hasArrangement: boolean;
  activeJobId: string | null;
  currentTab: string;
  onStepClick: (step: FlowStep) => void;
}

const STEPS: { id: FlowStep; labelKey: string; icon: React.ElementType; tab: string }[] = [
  { id: "upload",  labelKey: "העלה",   icon: Upload, tab: "analysis" },
  { id: "analyze", labelKey: "נתח",    icon: Zap,    tab: "analysis" },
  { id: "arrange", labelKey: "עיבוד",  icon: Layers, tab: "arrange"  },
  { id: "export",  labelKey: "ייצוא",  icon: Download, tab: "export" },
];

function getActiveStep(hasAudio: boolean, hasAnalysis: boolean, hasArrangement: boolean, activeJobId: string | null): FlowStep {
  if (!hasAudio) return "upload";
  if (!hasAnalysis) return "analyze";
  if (!hasArrangement) return "arrange";
  return "export";
}

function isStepDone(step: FlowStep, hasAudio: boolean, hasAnalysis: boolean, hasArrangement: boolean): boolean {
  if (step === "upload")  return hasAudio;
  if (step === "analyze") return hasAnalysis;
  if (step === "arrange") return hasArrangement;
  return false;
}

export function GuidedFlowBar({ hasAudio, hasAnalysis, hasArrangement, activeJobId, currentTab, onStepClick }: GuidedFlowBarProps) {
  const { t } = useTranslation();
  const activeStep = getActiveStep(hasAudio, hasAnalysis, hasArrangement, activeJobId);

  return (
    <div className="h-10 bg-[#0a0a0e] border-b border-white/5 flex items-center px-4 gap-1 rtl:flex-row-reverse" dir="rtl">
      {STEPS.map((step, i) => {
        const done = isStepDone(step.id, hasAudio, hasAnalysis, hasArrangement);
        const active = step.id === activeStep;
        const Icon = step.icon;
        return (
          <div key={step.id} className="flex items-center gap-1">
            {i > 0 && <ChevronLeft className="w-3 h-3 text-white/15 rtl:rotate-180 flex-shrink-0" />}
            <button
              onClick={() => onStepClick(step.id)}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1 rounded-md text-[11px] font-semibold transition-all tracking-wide",
                active && !done
                  ? "bg-primary/20 text-primary border border-primary/40 shadow-[0_0_8px_rgba(0,240,255,0.15)]"
                  : done
                  ? "text-green-400/80 hover:text-green-300 bg-green-400/5 hover:bg-green-400/10"
                  : "text-white/30 hover:text-white/50 hover:bg-white/5"
              )}
            >
              <Icon className="w-3 h-3 flex-shrink-0" />
              <span>{step.labelKey}</span>
              {done && <span className="w-1.5 h-1.5 rounded-full bg-green-400 flex-shrink-0" />}
              {active && !done && activeJobId && (
                <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse flex-shrink-0" />
              )}
            </button>
          </div>
        );
      })}
    </div>
  );
}
