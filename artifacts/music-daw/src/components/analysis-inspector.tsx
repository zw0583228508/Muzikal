import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import {
  Activity, Music2, Mic2, Layers, Waves, Clock,
  TrendingUp, AlertTriangle, CheckCircle2
} from "lucide-react";

interface AnalysisInspectorProps {
  analysis: any;
}

function ConfidenceBar({ value, label }: { value: number; label: string }) {
  const pct = Math.round(value * 100);
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-20 text-muted-foreground truncate">{label}</span>
      <div className="flex-1 h-2 bg-white/5 rounded-full overflow-hidden">
        <div
          className={cn(
            "h-full rounded-full transition-all duration-500",
            pct >= 80 ? "bg-green-500" : pct >= 55 ? "bg-yellow-500" : "bg-red-500"
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span
        className={cn(
          "w-9 text-right font-mono text-[11px]",
          pct >= 80 ? "text-green-400" : pct >= 55 ? "text-yellow-400" : "text-red-400"
        )}
        dir="ltr"
      >
        {pct}%
      </span>
    </div>
  );
}

function SectionTimeline({ sections }: { sections: any[] }) {
  const total = sections[sections.length - 1]?.endTime ?? 1;
  const COLORS: Record<string, string> = {
    intro:  "#6366f1",
    verse:  "#22c55e",
    chorus: "#00f0ff",
    bridge: "#f59e0b",
    outro:  "#ec4899",
    pre_chorus: "#a855f7",
    hook:   "#f97316",
  };
  return (
    <div className="relative h-8 rounded-md overflow-hidden bg-black/40 w-full" dir="ltr">
      {sections.map((s, i) => {
        const left = (s.startTime / total) * 100;
        const width = ((s.endTime - s.startTime) / total) * 100;
        const color = COLORS[s.label?.toLowerCase()] ?? "#4b5563";
        return (
          <div
            key={i}
            className="absolute top-0 h-full flex items-center justify-center text-[9px] font-bold text-white/80 overflow-hidden border-r border-black/40"
            style={{ left: `${left}%`, width: `${width}%`, backgroundColor: color + "99" }}
            title={`${s.label} (${s.startTime.toFixed(1)}s–${s.endTime.toFixed(1)}s) conf: ${Math.round((s.confidence ?? 0.8) * 100)}%`}
          >
            <span className="truncate px-1">{s.label}</span>
          </div>
        );
      })}
    </div>
  );
}

function ChordTimeline({ chords }: { chords: any[] }) {
  if (!chords?.length) return null;
  const total = chords[chords.length - 1]?.endTime ?? chords[chords.length - 1]?.startTime + 4 ?? 1;
  return (
    <div className="relative h-7 rounded-md overflow-hidden bg-black/40 w-full" dir="ltr">
      {chords.slice(0, 40).map((c, i) => {
        const start = c.startTime ?? 0;
        const end = c.endTime ?? start + 2;
        const left = (start / total) * 100;
        const width = Math.max(((end - start) / total) * 100, 2);
        const conf = c.confidence ?? 0.8;
        return (
          <div
            key={i}
            className="absolute top-0 h-full flex items-center justify-center text-[8px] font-mono text-white/80 border-r border-black/50"
            style={{
              left: `${left}%`,
              width: `${width}%`,
              backgroundColor: `rgba(0,240,255,${0.15 + conf * 0.35})`,
            }}
            title={`${c.chord} (conf: ${Math.round(conf * 100)}%)`}
          >
            {width > 4 && <span className="truncate px-0.5">{c.chord}</span>}
          </div>
        );
      })}
    </div>
  );
}

function MelodyPitchRange({ notes }: { notes: any[] }) {
  if (!notes?.length) return null;
  const pitches = notes.map((n: any) => n.midi ?? n.pitch ?? 60).filter(Boolean);
  const min = Math.min(...pitches);
  const max = Math.max(...pitches);
  const midiToNote = (m: number) => {
    const names = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"];
    return `${names[m % 12]}${Math.floor(m / 12) - 1}`;
  };
  const range = max - min;
  return (
    <div className="flex items-center gap-3 text-xs" dir="ltr">
      <span className="text-muted-foreground">Range</span>
      <div className="flex-1 h-3 bg-black/40 rounded-full overflow-hidden relative">
        <div
          className="absolute h-full bg-accent/50 rounded-full"
          style={{ left: `${((min - 36) / 60) * 100}%`, width: `${(range / 60) * 100}%` }}
        />
      </div>
      <span className="font-mono text-white/70">{midiToNote(min)} – {midiToNote(max)}</span>
    </div>
  );
}

export function AnalysisInspector({ analysis }: AnalysisInspectorProps) {
  const { t } = useTranslation();

  if (!analysis) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center space-y-3">
        <Activity className="w-12 h-12 text-muted-foreground opacity-20" />
        <p className="text-sm text-muted-foreground">{t("אין נתוני אנליזה עדיין.")}</p>
        <p className="text-xs text-muted-foreground/60">{t("הפעל אנליזה כדי לראות את הנתונים.")}</p>
      </div>
    );
  }

  const rhythm = analysis?.rhythm ?? {};
  const key = analysis?.key ?? {};
  const chords = analysis?.chords ?? {};
  const melody = analysis?.melody ?? {};
  const structure = analysis?.structure ?? {};
  const confidence = analysis?.confidenceData ?? {};
  const stems = analysis?.sourceSeparation ?? {};
  const warnings = analysis?.warnings ?? [];

  const sections: any[] = structure?.sections ?? [];
  const chordList: any[] = chords?.chords ?? [];
  const melodyNotes: any[] = melody?.notes ?? [];

  return (
    <div className="space-y-5 pb-4">
      {/* ── Warnings ── */}
      {warnings.length > 0 && (
        <div className="daw-panel p-3 border-amber-500/20">
          <div className="flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
            <div className="space-y-0.5">
              {warnings.slice(0, 3).map((w: string, i: number) => (
                <p key={i} className="text-[10px] text-amber-400/80">{w}</p>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ── Tempo & Time Signature ── */}
      <div className="daw-panel p-4 space-y-3">
        <div className="flex items-center gap-2 mb-1">
          <TrendingUp className="w-3.5 h-3.5 text-primary" />
          <h4 className="text-xs font-display font-bold text-muted-foreground uppercase tracking-widest">{t("ריתמוס")}</h4>
        </div>
        <div className="grid grid-cols-3 gap-3" dir="ltr">
          {[
            { label: "BPM", value: rhythm.bpm ? Math.round(rhythm.bpm) : "—" },
            { label: t("חתימה"), value: rhythm.timeSignatureNumerator ? `${rhythm.timeSignatureNumerator}/${rhythm.timeSignatureDenominator}` : "—" },
            { label: t("Beats"), value: rhythm.beatGrid?.length ?? "—" },
          ].map(({ label, value }) => (
            <div key={label} className="text-center bg-black/30 rounded-lg p-2">
              <div className="text-lg font-bold text-white">{value}</div>
              <div className="text-[9px] text-muted-foreground uppercase tracking-widest">{label}</div>
            </div>
          ))}
        </div>
        {rhythm.beatGrid?.length > 0 && (
          <div className="text-[10px] text-muted-foreground" dir="ltr">
            {rhythm.beatGrid.length} beats · {rhythm.downbeats?.length ?? 0} downbeats
          </div>
        )}
      </div>

      {/* ── Key / Mode ── */}
      <div className="daw-panel p-4 space-y-2">
        <div className="flex items-center gap-2 mb-1">
          <Music2 className="w-3.5 h-3.5 text-accent" />
          <h4 className="text-xs font-display font-bold text-muted-foreground uppercase tracking-widest">{t("מפתח")}</h4>
        </div>
        <div className="flex items-baseline gap-2" dir="ltr">
          <span className="text-2xl font-bold text-white">{key.globalKey ?? "—"}</span>
          <span className="text-sm text-muted-foreground capitalize">{key.mode ?? ""}</span>
          {key.confidence !== undefined && (
            <span className={cn("ml-auto text-xs font-mono", key.confidence > 0.75 ? "text-green-400" : "text-yellow-400")}>
              {Math.round(key.confidence * 100)}%
            </span>
          )}
        </div>
        {key.alternatives?.length > 0 && (
          <div className="flex gap-1 flex-wrap" dir="ltr">
            {key.alternatives.slice(0, 3).map((alt: any, i: number) => (
              <span key={i} className="px-2 py-0.5 rounded bg-white/5 text-[10px] font-mono text-white/50">
                {alt.key} {alt.mode} <span className="text-white/30">{Math.round((alt.confidence ?? 0) * 100)}%</span>
              </span>
            ))}
          </div>
        )}
      </div>

      {/* ── Chord Timeline ── */}
      <div className="daw-panel p-4 space-y-3">
        <div className="flex items-center gap-2 mb-1">
          <Waves className="w-3.5 h-3.5 text-primary" />
          <h4 className="text-xs font-display font-bold text-muted-foreground uppercase tracking-widest">{t("אקורדים")}</h4>
          <span className="ml-auto text-[10px] text-muted-foreground">{chordList.length} {t("אקורדים")}</span>
        </div>
        {chordList.length > 0 ? (
          <>
            <ChordTimeline chords={chordList} />
            <div className="text-[10px] text-muted-foreground" dir="ltr">
              {chords.leadSheet ?? chordList.slice(0, 8).map((c: any) => c.chord).join(" | ")}
            </div>
          </>
        ) : (
          <p className="text-xs text-muted-foreground">{t("אין נתוני אקורדים")}</p>
        )}
      </div>

      {/* ── Melody ── */}
      <div className="daw-panel p-4 space-y-3">
        <div className="flex items-center gap-2 mb-1">
          <Music2 className="w-3.5 h-3.5 text-accent" />
          <h4 className="text-xs font-display font-bold text-muted-foreground uppercase tracking-widest">{t("מלודיה")}</h4>
          <span className="ml-auto text-[10px] text-muted-foreground">{melodyNotes.length} {t("תווים")}</span>
        </div>
        <MelodyPitchRange notes={melodyNotes} />
        {melody.inferredHarmony?.length > 0 && (
          <div className="text-[10px] text-muted-foreground" dir="ltr">
            {melody.inferredHarmony.slice(0, 2).join(" · ")}
          </div>
        )}
      </div>

      {/* ── Structure Timeline ── */}
      <div className="daw-panel p-4 space-y-3">
        <div className="flex items-center gap-2 mb-1">
          <Layers className="w-3.5 h-3.5 text-primary" />
          <h4 className="text-xs font-display font-bold text-muted-foreground uppercase tracking-widest">{t("מבנה")}</h4>
          <span className="ml-auto text-[10px] text-muted-foreground">{sections.length} {t("חלקים")}</span>
        </div>
        {sections.length > 0 ? (
          <>
            <SectionTimeline sections={sections} />
            <div className="space-y-1">
              {sections.map((s, i) => (
                <div key={i} className="flex items-center gap-2 text-[11px]" dir="ltr">
                  <span className="capitalize text-white/70 w-16 truncate">{s.label}</span>
                  <span className="text-muted-foreground font-mono">{s.startTime?.toFixed(1)}s – {s.endTime?.toFixed(1)}s</span>
                  <div className="ml-auto h-1.5 w-12 bg-white/5 rounded-full overflow-hidden">
                    <div
                      className={cn("h-full rounded-full", (s.confidence ?? 0.8) > 0.75 ? "bg-green-500" : "bg-yellow-500")}
                      style={{ width: `${Math.round((s.confidence ?? 0.8) * 100)}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </>
        ) : (
          <p className="text-xs text-muted-foreground">{t("אין נתוני מבנה")}</p>
        )}
      </div>

      {/* ── Stem Separation ── */}
      <div className="daw-panel p-4 space-y-2">
        <div className="flex items-center gap-2 mb-1">
          <Mic2 className="w-3.5 h-3.5 text-accent" />
          <h4 className="text-xs font-display font-bold text-muted-foreground uppercase tracking-widest">{t("הפרדת Stems")}</h4>
        </div>
        <div className="flex items-center gap-2 text-xs" dir="ltr">
          <span className="text-muted-foreground">{t("שיטה")}:</span>
          <span className="font-mono text-white/70">{stems.method ?? "none"}</span>
        </div>
        {stems.stems?.length > 0 ? (
          <div className="flex flex-wrap gap-1" dir="ltr">
            {stems.stems.map((s: string) => (
              <span key={s} className="px-2 py-0.5 rounded bg-green-500/10 border border-green-500/20 text-[10px] text-green-400 flex items-center gap-1">
                <CheckCircle2 className="w-2.5 h-2.5" />{s}
              </span>
            ))}
          </div>
        ) : (
          <p className="text-[10px] text-muted-foreground">{t("לא בוצעה הפרדה")}</p>
        )}
      </div>

      {/* ── Confidence Scores ── */}
      {Object.keys(confidence).length > 0 && (
        <div className="daw-panel p-4 space-y-2">
          <div className="flex items-center gap-2 mb-1">
            <Activity className="w-3.5 h-3.5 text-primary" />
            <h4 className="text-xs font-display font-bold text-muted-foreground uppercase tracking-widest">{t("רמות ביטחון")}</h4>
          </div>
          <div className="space-y-2">
            {(["overall", "rhythm", "key", "chords", "melody", "structure", "vocals"] as const).map(k => {
              const val = confidence[k];
              if (val === undefined) return null;
              const labelMap: Record<string, string> = {
                overall: t("כולל"), rhythm: t("ריתמוס"), key: t("מפתח"),
                chords: t("אקורדים"), melody: t("מלודיה"), structure: t("מבנה"), vocals: t("קולות"),
              };
              return <ConfidenceBar key={k} value={val} label={labelMap[k] ?? k} />;
            })}
          </div>
        </div>
      )}

      {/* ── Model Versions ── */}
      {analysis?.modelVersions && Object.keys(analysis.modelVersions).length > 0 && (
        <div className="daw-panel p-4 space-y-2">
          <div className="flex items-center gap-2 mb-1">
            <Clock className="w-3.5 h-3.5 text-primary" />
            <h4 className="text-xs font-display font-bold text-muted-foreground uppercase tracking-widest">{t("גרסאות מודלים")}</h4>
          </div>
          <div className="grid grid-cols-1 gap-1" dir="ltr">
            {Object.entries(analysis.modelVersions as Record<string, string>).map(([task, version]) => (
              <div key={task} className="flex items-center justify-between text-[10px]">
                <span className="text-muted-foreground capitalize">{task}</span>
                <span className="font-mono text-white/60 bg-white/5 px-1.5 py-0.5 rounded text-[9px]">{version}</span>
              </div>
            ))}
          </div>
          {typeof analysis?.cacheHitCount === "number" && (
            <div className="text-[10px] text-muted-foreground/50 pt-1" dir="ltr">
              cache hits: {analysis.cacheHitCount}/{Object.keys(analysis.modelVersions).length} steps
            </div>
          )}
        </div>
      )}

      {/* ── Pipeline metadata ── */}
      {analysis?.pipelineVersion && (
        <div className="text-[10px] text-muted-foreground/40 text-center" dir="ltr">
          pipeline v{analysis.pipelineVersion}
          {analysis?.cacheEnabled && " · cache ✓"}
        </div>
      )}
    </div>
  );
}
