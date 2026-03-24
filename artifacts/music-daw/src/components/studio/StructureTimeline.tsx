import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import { formatTime } from "@/lib/utils";

interface Section {
  label: string;
  start?: number;
  startTime?: number;
  end?: number;
  endTime?: number;
  duration?: number;
  energy?: number;
  confidence?: number;
  group_id?: number;
}

interface StructureTimelineProps {
  sections: Section[];
  totalDuration?: number;
  currentTime?: number;
  onSectionClick?: (section: Section, index: number) => void;
}

const SECTION_COLORS: Record<string, string> = {
  intro:        "bg-blue-500/60  border-blue-400/40",
  verse:        "bg-violet-500/60 border-violet-400/40",
  "pre-chorus": "bg-amber-500/60  border-amber-400/40",
  chorus:       "bg-cyan-500/70   border-cyan-400/50",
  bridge:       "bg-orange-500/60 border-orange-400/40",
  hook:         "bg-cyan-500/70   border-cyan-400/50",
  outro:        "bg-blue-400/40   border-blue-300/30",
  solo:         "bg-green-500/60  border-green-400/40",
  breakdown:    "bg-red-500/50    border-red-400/30",
  fill:         "bg-white/20      border-white/20",
};

const SECTION_LABELS_HE: Record<string, string> = {
  intro:        "פתיחה",
  verse:        "בית",
  "pre-chorus": "פרה-פזמון",
  chorus:       "פזמון",
  bridge:       "גשר",
  hook:         "הוק",
  outro:        "סיום",
  solo:         "סולו",
  breakdown:    "בריקדאון",
  fill:         "פיל",
};

function getColorClass(label: string): string {
  const key = label?.toLowerCase() ?? "";
  return SECTION_COLORS[key] ?? "bg-white/20 border-white/15";
}

export function StructureTimeline({ sections, totalDuration, currentTime, onSectionClick }: StructureTimelineProps) {
  const { t } = useTranslation();

  if (!sections?.length) return null;

  const total = totalDuration ?? Math.max(...sections.map(s => {
    const end = s.end ?? s.endTime ?? 0;
    return end;
  })) ?? 1;

  return (
    <div className="space-y-1.5">
      {/* Proportional horizontal timeline strip */}
      <div className="w-full h-8 rounded-lg overflow-hidden flex relative border border-white/5" dir="ltr">
        {sections.map((sec, i) => {
          const sStart = sec.start ?? sec.startTime ?? 0;
          const sEnd = sec.end ?? sec.endTime ?? (sStart + (sec.duration ?? 0));
          const widthPct = total > 0 ? ((sEnd - sStart) / total) * 100 : 0;
          const leftPct  = total > 0 ? (sStart / total) * 100 : 0;
          const isCurrent = currentTime !== undefined && currentTime >= sStart && currentTime < sEnd;

          return (
            <div
              key={i}
              className={cn(
                "absolute h-full border-r border-r-black/30 flex items-center justify-center transition-all cursor-pointer",
                getColorClass(sec.label),
                isCurrent && "ring-2 ring-white/60 ring-inset z-10"
              )}
              style={{ left: `${leftPct}%`, width: `${widthPct}%` }}
              title={`${t(sec.label)} — ${formatTime(sStart)}–${formatTime(sEnd)}`}
              onClick={() => onSectionClick?.(sec, i)}
            >
              {widthPct > 8 && (
                <span className="text-[9px] font-bold text-white/90 uppercase tracking-wider truncate px-1">
                  {SECTION_LABELS_HE[sec.label?.toLowerCase()] ?? t(sec.label)}
                </span>
              )}
            </div>
          );
        })}
        {/* Playhead */}
        {currentTime !== undefined && total > 0 && (
          <div
            className="absolute top-0 h-full w-0.5 bg-white/80 z-20 pointer-events-none"
            style={{ left: `${(currentTime / total) * 100}%` }}
          />
        )}
      </div>

      {/* Section list rows */}
      <div className="space-y-1">
        {sections.map((sec, i) => {
          const sStart = sec.start ?? sec.startTime ?? 0;
          const sEnd = sec.end ?? sec.endTime ?? (sStart + (sec.duration ?? 0));
          const dur = sEnd - sStart;
          const energy = sec.energy ?? 0;
          const conf = sec.confidence;

          return (
            <div
              key={i}
              className="flex items-center gap-2 px-2 py-1 rounded hover:bg-white/5 transition-colors group cursor-pointer"
              onClick={() => onSectionClick?.(sec, i)}
            >
              {/* Color dot */}
              <div className={cn("w-2 h-2 rounded-full flex-shrink-0", getColorClass(sec.label).split(" ")[0].replace("/60","/90").replace("/70","/90").replace("/40","/80").replace("/50","/80"))} />

              {/* Label */}
              <span className="text-xs text-white/80 capitalize w-20 flex-shrink-0">
                {SECTION_LABELS_HE[sec.label?.toLowerCase()] ?? t(sec.label)}
              </span>

              {/* Energy bar */}
              <div className="flex-1 h-1 bg-white/5 rounded-full overflow-hidden">
                <div
                  className={cn("h-full rounded-full transition-all", energy > 0.7 ? "bg-cyan-400/70" : energy > 0.4 ? "bg-violet-400/60" : "bg-white/20")}
                  style={{ width: `${Math.round(energy * 100)}%` }}
                />
              </div>

              {/* Time */}
              <span className="text-[10px] font-mono text-muted-foreground flex-shrink-0" dir="ltr">
                {formatTime(sStart)}
              </span>

              {/* Duration */}
              <span className="text-[9px] text-white/25 flex-shrink-0" dir="ltr">
                {dur.toFixed(0)}s
              </span>

              {/* Confidence */}
              {conf !== undefined && (
                <span className={cn("text-[9px] font-mono flex-shrink-0",
                  conf > 0.75 ? "text-green-400/80" : conf > 0.5 ? "text-yellow-400/80" : "text-red-400/70"
                )}>
                  {Math.round(conf * 100)}%
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
