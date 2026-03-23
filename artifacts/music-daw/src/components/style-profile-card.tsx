import { useState } from "react";
import { CheckCircle2, Loader2, Edit2, Music2, Drum, Guitar, Clock, Gauge, Waves } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

interface InstrumentConfig {
  name: string;
  role: string;
  midiProgram?: number;
  volumeWeight?: number;
  panPosition?: number;
  playingStyle?: string;
}

interface StyleProfile {
  genre?: string;
  era?: string;
  subStyle?: string;
  region?: string;
  scaleType?: string;
  chordVocabulary?: string[];
  timeSignature?: string;
  bpmRange?: [number, number];
  rhythmPattern?: string;
  swingFactor?: number;
  instruments?: InstrumentConfig[];
  voicingStyle?: string;
  textureType?: string;
  sectionLabels?: string[];
  formTemplate?: string;
  ornamentStyle?: string;
  dynamicsProfile?: string;
  reverbRoom?: string;
  humanizationLevel?: number;
  isFallback?: boolean;
  detectedKey?: string;
  [key: string]: unknown;
}

interface StyleProfileCardProps {
  profile: Record<string, unknown>;
  onConfirm?: () => void;
  confirming?: boolean;
  className?: string;
}

const ROLE_ICONS: Record<string, React.ReactNode> = {
  MELODY_LEAD: <Music2 className="w-3 h-3" />,
  MELODY_COUNTER: <Music2 className="w-3 h-3 opacity-70" />,
  HARMONY_CHORD: <Guitar className="w-3 h-3" />,
  HARMONY_PAD: <Waves className="w-3 h-3" />,
  BASS: <Gauge className="w-3 h-3" />,
  RHYTHM_KICK: <Drum className="w-3 h-3" />,
  RHYTHM_SNARE: <Drum className="w-3 h-3 opacity-70" />,
  RHYTHM_PERC: <Drum className="w-3 h-3 opacity-50" />,
  COLOR: <Waves className="w-3 h-3" />,
  DRONE: <Waves className="w-3 h-3 opacity-60" />,
};

const ROLE_COLORS: Record<string, string> = {
  MELODY_LEAD: "bg-violet-500/20 text-violet-300 border-violet-500/30",
  MELODY_COUNTER: "bg-violet-500/10 text-violet-400 border-violet-500/20",
  HARMONY_CHORD: "bg-blue-500/20 text-blue-300 border-blue-500/30",
  HARMONY_PAD: "bg-blue-500/10 text-blue-400 border-blue-500/20",
  BASS: "bg-amber-500/20 text-amber-300 border-amber-500/30",
  RHYTHM_KICK: "bg-red-500/20 text-red-300 border-red-500/30",
  RHYTHM_SNARE: "bg-orange-500/20 text-orange-300 border-orange-500/30",
  RHYTHM_PERC: "bg-orange-500/10 text-orange-400 border-orange-500/20",
  COLOR: "bg-emerald-500/20 text-emerald-300 border-emerald-500/30",
  DRONE: "bg-zinc-500/20 text-zinc-300 border-zinc-500/30",
};

function InstrumentBadge({ inst }: { inst: InstrumentConfig }) {
  const colorClass = ROLE_COLORS[inst.role] ?? "bg-zinc-800 text-zinc-300 border-zinc-700";
  return (
    <div className={cn("flex items-center gap-1 px-2 py-1 rounded-full border text-xs font-medium", colorClass)}>
      {ROLE_ICONS[inst.role]}
      <span>{inst.name}</span>
    </div>
  );
}

function FieldRow({ label, value }: { label: string; value: React.ReactNode }) {
  if (!value) return null;
  return (
    <div className="flex items-start gap-2 text-xs">
      <span className="text-zinc-500 w-24 shrink-0">{label}</span>
      <span className="text-zinc-200">{value}</span>
    </div>
  );
}

export default function StyleProfileCard({
  profile,
  onConfirm,
  confirming,
  className,
}: StyleProfileCardProps) {
  const p = profile as StyleProfile;
  const instruments = (p.instruments as InstrumentConfig[]) ?? [];
  const bpmRange = p.bpmRange as [number, number] | undefined;
  const chords = (p.chordVocabulary as string[]) ?? [];

  return (
    <div
      className={cn(
        "rounded-xl border border-indigo-500/30 bg-indigo-950/40 p-4 space-y-4",
        className,
      )}
      dir="rtl"
    >
      {/* Title row */}
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-base font-bold text-white">
              {String(p.genre ?? "סגנון מוזיקלי")}
            </h3>
            {p.isFallback && (
              <Badge variant="outline" className="border-amber-500 text-amber-600 dark:text-amber-400 text-[10px]">
                Fallback — AI data unavailable
              </Badge>
            )}
          </div>
          <p className="text-xs text-zinc-400 mt-0.5">
            {[p.subStyle, p.era, p.region].filter(Boolean).join(" · ")}
          </p>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <div className="w-2 h-2 rounded-full bg-emerald-500" />
          <span className="text-xs text-emerald-400 font-medium">מוכן</span>
        </div>
      </div>

      {/* Rhythm + harmony */}
      <div className="grid grid-cols-2 gap-2">
        <div className="bg-zinc-900/50 rounded-lg p-2.5 space-y-1.5">
          <div className="text-[10px] font-semibold text-zinc-500 uppercase tracking-wider flex items-center gap-1">
            <Clock className="w-3 h-3" /> קצב
          </div>
          <FieldRow label="משקל" value={p.timeSignature} />
          <FieldRow
            label="BPM"
            value={bpmRange ? `${bpmRange[0]}–${bpmRange[1]}` : undefined}
          />
          <FieldRow label="פטרן" value={p.rhythmPattern} />
          {(p.swingFactor as number) > 0 && (
            <FieldRow label="סווינג" value={`${Math.round((p.swingFactor as number) * 100)}%`} />
          )}
        </div>
        <div className="bg-zinc-900/50 rounded-lg p-2.5 space-y-1.5">
          <div className="text-[10px] font-semibold text-zinc-500 uppercase tracking-wider flex items-center gap-1">
            <Music2 className="w-3 h-3" /> הרמוניה
          </div>
          <FieldRow label="סולם" value={p.scaleType} />
          {p.detectedKey && <FieldRow label="מפתח" value={p.detectedKey} />}
          <FieldRow
            label="אקורדים"
            value={chords.length > 0 ? chords.slice(0, 4).join(" · ") : undefined}
          />
          <FieldRow label="מודולציה" value={p.modulationTendency as string} />
        </div>
      </div>

      {/* Instruments */}
      {instruments.length > 0 && (
        <div>
          <div className="text-[10px] font-semibold text-zinc-500 uppercase tracking-wider mb-2 flex items-center gap-1">
            <Guitar className="w-3 h-3" /> כלים ({instruments.length})
          </div>
          <div className="flex flex-wrap gap-1.5">
            {instruments.map((inst, i) => (
              <InstrumentBadge key={i} inst={inst} />
            ))}
          </div>
        </div>
      )}

      {/* Additional fields */}
      <div className="grid grid-cols-2 gap-x-4 gap-y-1">
        <FieldRow label="טקסטורה" value={p.textureType as string} />
        <FieldRow label="ווייסינג" value={p.voicingStyle as string} />
        <FieldRow label="קישוטים" value={p.ornamentStyle as string} />
        <FieldRow label="חדר" value={p.reverbRoom as string} />
        <FieldRow
          label="אנושיות"
          value={
            (p.humanizationLevel as number) != null
              ? `${Math.round((p.humanizationLevel as number) * 100)}%`
              : undefined
          }
        />
        <FieldRow label="מבנה" value={p.formTemplate as string} />
      </div>

      {/* Section labels */}
      {p.sectionLabels && (p.sectionLabels as string[]).length > 0 && (
        <div className="flex flex-wrap gap-1">
          {(p.sectionLabels as string[]).map((s) => (
            <Badge key={s} variant="secondary" className="text-[10px] bg-zinc-800 text-zinc-300">
              {s}
            </Badge>
          ))}
        </div>
      )}

      {/* Confirm button */}
      {onConfirm && (
        <Button
          onClick={onConfirm}
          disabled={confirming}
          className="w-full bg-indigo-600 hover:bg-indigo-500 text-white font-semibold"
        >
          {confirming ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin ml-2" />
              שולח לעיבוד...
            </>
          ) : (
            <>
              <CheckCircle2 className="w-4 h-4 ml-2" />
              אשר ובצע עיבוד
            </>
          )}
        </Button>
      )}
    </div>
  );
}
