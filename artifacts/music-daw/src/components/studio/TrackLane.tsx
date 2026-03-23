import { useTranslation } from "react-i18next";
import { Slider } from "@/components/ui/slider";
import { Piano, Volume2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface TrackLaneProps {
  track: any;
  isSelected: boolean;
  onSelect: () => void;
  onRegen?: (trackId: string) => void;
}

export function TrackLane({ track, isSelected, onSelect, onRegen }: TrackLaneProps) {
  const { t } = useTranslation();
  return (
    <div
      className={cn("flex border-b border-white/5 h-24 group relative cursor-pointer", isSelected && "ring-1 ring-inset ring-primary/40")}
      onClick={onSelect}
    >
      <div className={cn("w-64 border-r border-white/10 flex flex-col justify-center px-3 z-10 transition-colors", isSelected ? "bg-primary/10" : "bg-card")}>
        <div className="flex justify-between items-center mb-2">
          <span className="font-medium text-sm text-white truncate flex items-center gap-2">
            <div className="w-2 h-2 rounded-full" style={{ backgroundColor: track.color || '#00f0ff' }} />
            {t(track.name)}
          </span>
          <div className="flex gap-1" dir="ltr" onClick={e => e.stopPropagation()}>
            <button
              className={cn("w-6 h-6 rounded text-xs font-bold transition-colors", track.muted ? "bg-accent/20 text-accent" : "bg-white/5 hover:bg-white/10")}
              title={t("Mute")}
            >M</button>
            <button
              className={cn("w-6 h-6 rounded text-xs font-bold transition-colors", track.soloed ? "bg-yellow-500/20 text-yellow-500" : "bg-white/5 hover:bg-white/10")}
              title={t("Solo")}
            >S</button>
            {onRegen && (
              <button
                className="w-6 h-6 rounded text-xs font-bold transition-colors bg-accent/10 text-accent/70 hover:bg-accent/20 hover:text-accent"
                title={t("Regenerate track")}
                onClick={e => { e.stopPropagation(); onRegen(track.id); }}
              >↺</button>
            )}
            <button
              className="w-6 h-6 rounded text-xs font-bold transition-colors bg-primary/10 text-primary hover:bg-primary/20"
              title={t("Open Piano Roll")}
            ><Piano className="w-3 h-3 mx-auto" /></button>
          </div>
        </div>
        <div className="flex items-center gap-2" dir="ltr" onClick={e => e.stopPropagation()}>
          <Volume2 className="w-3 h-3 text-muted-foreground" />
          <Slider defaultValue={[track.volume * 100]} max={100} className="w-full" />
        </div>
      </div>

      <div className="flex-1 bg-[#0a0a0c] relative overflow-hidden" dir="ltr">
        <div className="absolute inset-0 bg-[linear-gradient(90deg,rgba(255,255,255,0.015)_1px,transparent_1px)] bg-[size:2rem_100%]" />
        {track.notes?.slice(0, 100).map((note: any, i: number) => (
          <div
            key={i}
            className="absolute rounded-sm"
            style={{
              left: `${note.startTime * 20}px`,
              width: `${Math.max(note.duration * 20, 2)}px`,
              bottom: `${Math.max(0, (note.pitch - 36) % 52) * 1.7 + 4}px`,
              height: 3,
              backgroundColor: track.color || '#00f0ff',
              opacity: 0.4 + (note.velocity / 127) * 0.6,
            }}
          />
        ))}
        {isSelected && (
          <div className="absolute inset-0 flex items-center justify-center">
            <span className="text-xs text-primary/60 bg-black/40 px-2 py-0.5 rounded">{t("Open Piano Roll")} ↓</span>
          </div>
        )}
      </div>
    </div>
  );
}
