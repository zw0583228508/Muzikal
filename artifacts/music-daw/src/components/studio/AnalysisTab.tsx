import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { AnalysisInspector } from "@/components/analysis-inspector";
import { Activity, Zap, Upload, Lock, Unlock } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatTime } from "@/lib/utils";

interface AnalysisTabProps {
  analysis: any;
  project: any;
  projectId: number;
  activeJobId: string | null;
  isMockMode: boolean;
  modelVersions: Record<string, string>;
  lockedFields: Set<string>;
  chordOverrides: Record<number, string>;
  editingChordIdx: number | null;
  onAnalyze: () => void;
  onUploadClick: () => void;
  onToggleLock: (field: string) => void;
  onSetChordOverride: (idx: number, chord: string) => void;
  onSetEditingChordIdx: (idx: number | null) => void;
}

export function AnalysisTab({
  analysis,
  project,
  projectId,
  activeJobId,
  isMockMode,
  modelVersions,
  lockedFields,
  chordOverrides,
  editingChordIdx,
  fileInputRef,
  onAnalyze,
  onUploadClick,
  onToggleLock,
  onSetChordOverride,
  onSetEditingChordIdx,
}: AnalysisTabProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();

  if (!analysis) {
    return (
      <div className="text-center py-10 space-y-4">
        <Activity className="w-12 h-12 text-muted-foreground mx-auto opacity-20" />
        <p className="text-sm text-muted-foreground">{t("No analysis data yet.")}</p>
        <Button
          onClick={onAnalyze}
          disabled={(!!activeJobId) || (!project?.audioFileName && !isMockMode)}
          className="w-full"
        >
          <Zap className="w-4 h-4 mr-2" /> {t("Start Analysis")}
        </Button>
        {!project?.audioFileName && !isMockMode && (
          <>
            <Button variant="outline" className="w-full" onClick={onUploadClick}>
              <Upload className="w-4 h-4 mr-2" /> {t("Upload Audio")}
            </Button>
          </>
        )}
        {!project?.audioFileName && isMockMode && (
          <p className="text-xs text-amber-400/70">{t("MOCK MODE — analysis runs on simulated data")}</p>
        )}
      </div>
    );
  }

  return (
    <>
      {/* Key & Time */}
      <div className="daw-panel p-4 space-y-3">
        <div className="flex justify-between text-sm">
          <div className="space-y-0.5">
            <p className="text-muted-foreground text-[10px] uppercase tracking-wider">{t("Key")}</p>
            <p className="text-primary font-bold font-display text-lg" dir="ltr">
              {analysis.key?.globalKey} <span className="text-primary/60 text-sm">{analysis.key?.mode}</span>
            </p>
          </div>
          <div className="space-y-0.5 text-right">
            <p className="text-muted-foreground text-[10px] uppercase tracking-wider">{t("BPM")}</p>
            <p className="text-accent font-bold font-display text-lg" dir="ltr">{Math.round(analysis.rhythm?.bpm ?? 0)}</p>
          </div>
          <div className="space-y-0.5 text-center">
            <p className="text-muted-foreground text-[10px] uppercase tracking-wider">{t("Time")}</p>
            <p className="text-white font-bold font-display text-lg" dir="ltr">
              {analysis.rhythm?.timeSignatureNumerator ?? 4}/{analysis.rhythm?.timeSignatureDenominator ?? 4}
            </p>
          </div>
        </div>
      </div>

      {/* Song Structure */}
      <div className="daw-panel p-4">
        <h4 className="text-xs font-display font-bold text-muted-foreground uppercase tracking-widest mb-3">{t("Structure")}</h4>
        <div className="space-y-1.5">
          {(analysis.structure?.sections ?? []).map((sec: any, i: number) => (
            <div
              key={i}
              className={cn(
                "flex items-center justify-between px-3 py-2 rounded-lg transition-colors group cursor-pointer",
                sec.regenerate ? "bg-accent/10 border border-accent/30" : "bg-white/5 hover:bg-white/8"
              )}
            >
              <div className="flex items-center gap-2">
                {sec.locked
                  ? <Lock className="w-3 h-3 text-primary flex-shrink-0" />
                  : <div
                      className="w-2 h-2 rounded-full flex-shrink-0"
                      style={{ backgroundColor: sec.label === "chorus" ? "#00f0ff" : sec.label === "verse" ? "#a855f7" : "#888" }}
                    />
                }
                <span className="capitalize text-white/80 text-xs">{t(sec.label)}</span>
                {sec.regenerate && <span className="text-[9px] text-accent uppercase">{t("Queued")}</span>}
              </div>
              <div className="flex items-center gap-2" dir="ltr">
                <span className="text-muted-foreground font-mono text-[10px]">{formatTime(sec.startTime)}</span>
                {sec.confidence !== undefined && (
                  <span className={cn("text-[9px] font-mono", sec.confidence > 0.75 ? "text-green-400" : sec.confidence > 0.5 ? "text-yellow-400" : "text-red-400")}>
                    {Math.round(sec.confidence * 100)}%
                  </span>
                )}
                <button
                  className="opacity-0 group-hover:opacity-100 transition-opacity text-accent/70 hover:text-accent"
                  title={t("Regenerate this section")}
                  onClick={() => {
                    fetch(`/api/projects/${projectId}/regenerate-section`, {
                      method: "POST",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({ sectionIndex: i }),
                    }).then(() => queryClient.invalidateQueries({ queryKey: [`/api/projects/${projectId}/analysis`] }));
                  }}
                >
                  <Zap className="w-3 h-3" />
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Confidence overview */}
      {analysis.confidenceData && (
        <div className="daw-panel p-4">
          <h4 className="text-xs font-display font-bold text-muted-foreground uppercase tracking-widest mb-3">{t("Analysis Confidence")}</h4>
          <div className="space-y-1.5">
            {(["rhythm", "key", "chords", "melody", "structure"] as const).map(mod => {
              const val = analysis.confidenceData[mod];
              if (val === undefined) return null;
              const pct = Math.round(val * 100);
              return (
                <div key={mod} className="flex items-center gap-2 text-xs">
                  <span className="w-16 text-muted-foreground capitalize">{t(mod)}</span>
                  <div className="flex-1 h-1.5 bg-white/5 rounded-full overflow-hidden">
                    <div
                      className={cn("h-full rounded-full transition-all", pct > 75 ? "bg-green-500" : pct > 50 ? "bg-yellow-500" : "bg-red-500")}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                  <span className="w-8 text-right font-mono text-white/50" dir="ltr">{pct}%</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Chord Progression */}
      <div className={cn("daw-panel p-4 transition-all", lockedFields.has("chords") && "ring-1 ring-primary/40 shadow-[0_0_10px_rgba(0,240,255,0.08)]")}>
        <div className="flex items-center justify-between mb-3">
          <h4 className="text-xs font-display font-bold text-muted-foreground uppercase tracking-widest">{t("Chord Progression")}</h4>
          <div className="flex items-center gap-2">
            {Object.keys(chordOverrides).length > 0 && (
              <button
                onClick={() => onSetChordOverride(-1, "")}
                className="text-[10px] text-accent/70 hover:text-accent transition-colors"
                title={t("Reset all chord edits")}
              >
                {t("Reset")}
              </button>
            )}
            <button
              onClick={() => onToggleLock("chords")}
              className={cn(
                "w-6 h-6 rounded flex items-center justify-center transition-colors",
                lockedFields.has("chords") ? "text-primary bg-primary/20" : "text-muted-foreground hover:text-white bg-white/5 hover:bg-white/10"
              )}
              title={lockedFields.has("chords") ? t("Unlock field") : t("Lock field")}
            >
              {lockedFields.has("chords") ? <Lock className="w-3 h-3" /> : <Unlock className="w-3 h-3" />}
            </button>
          </div>
        </div>
        {analysis.chords?.chords?.length > 0 ? (
          <div className="flex flex-wrap gap-1" dir="ltr">
            {(analysis.chords.chords as any[]).slice(0, 16).map((c: any, i: number) => {
              const displayed = chordOverrides[i] ?? c.chord;
              const isEditing = editingChordIdx === i;
              return (
                <div key={i} className="relative">
                  <button
                    onClick={() => onSetEditingChordIdx(isEditing ? null : i)}
                    className={cn(
                      "px-2 py-1 rounded text-xs font-mono border transition-all",
                      chordOverrides[i]
                        ? "bg-accent/20 border-accent/50 text-accent"
                        : "bg-primary/15 border-primary/30 text-primary/90 hover:bg-primary/25 hover:border-primary/60",
                      isEditing && "ring-1 ring-accent shadow-[0_0_8px_rgba(0,240,255,0.3)]"
                    )}
                    title={c.alternatives?.length ? `${t("Alternatives")}: ${c.alternatives.join(", ")}` : undefined}
                  >
                    {displayed}
                    {c.confidence !== undefined && c.confidence < 0.5 && (
                      <span className="ml-1 text-[8px] text-yellow-400/70">?</span>
                    )}
                  </button>
                  {isEditing && (
                    <div className="absolute bottom-full mb-1 left-0 z-50 bg-card border border-white/20 rounded shadow-xl p-2 min-w-[120px]">
                      <p className="text-[10px] text-muted-foreground mb-1.5">{t("Select chord")}</p>
                      <div className="space-y-1">
                        {[c.chord, ...(c.alternatives ?? [])].map((alt: string) => (
                          <button
                            key={alt}
                            onClick={() => {
                              onSetChordOverride(i, alt);
                              onSetEditingChordIdx(null);
                            }}
                            className={cn(
                              "w-full text-left px-2 py-1 rounded text-xs font-mono transition-colors",
                              alt === displayed ? "bg-primary/20 text-primary" : "hover:bg-white/10 text-white/80"
                            )}
                          >
                            {alt}
                          </button>
                        ))}
                      </div>
                      {c.confidence !== undefined && (
                        <p className="text-[9px] text-muted-foreground mt-1.5 border-t border-white/10 pt-1">
                          {t("Confidence")}: {Math.round(c.confidence * 100)}%
                        </p>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        ) : (
          <p className="text-sm font-mono text-white/80 leading-relaxed" dir="ltr">
            {analysis.chords?.leadSheet}
          </p>
        )}
      </div>

      <Button variant="outline" className="w-full" onClick={onAnalyze} disabled={!!activeJobId}>
        <Zap className="w-4 h-4 mr-2" /> {t("Re-analyze")}
      </Button>

      {Object.keys(modelVersions).length > 0 && (
        <div className="daw-panel p-3 space-y-1">
          <h4 className="text-[10px] font-display font-bold text-muted-foreground uppercase tracking-widest mb-2">{t("Models")}</h4>
          {Object.entries(modelVersions).map(([model, version]) => (
            <div key={model} className="flex justify-between text-[10px]" dir="ltr">
              <span className="text-muted-foreground">{model}</span>
              <span className="text-primary/70 font-mono">{String(version)}</span>
            </div>
          ))}
        </div>
      )}
    </>
  );
}
