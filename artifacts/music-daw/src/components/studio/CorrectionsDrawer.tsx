import { useState, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Edit3, XCircle, CheckCircle2, Loader2, Music2, Layers, RotateCcw } from "lucide-react";
import { cn } from "@/lib/utils";
import { useQuery, useQueryClient } from "@tanstack/react-query";

interface CorrectionsDrawerProps {
  analysis: any;
  projectId: number;
  onClose: () => void;
  onSaved: (dependentStages: string[]) => void;
}

const KEYS = ["C", "C#", "Db", "D", "D#", "Eb", "E", "F", "F#", "Gb", "G", "G#", "Ab", "A", "A#", "Bb", "B"];
const MODES = ["major", "minor", "dorian", "phrygian", "lydian", "mixolydian", "aeolian", "locrian"];
const CHORD_QUALITIES = ["maj", "min", "dim", "aug", "maj7", "min7", "7", "dim7", "hdim7", "sus2", "sus4", "add9"];

type Tab = "global" | "sections" | "chords";

interface SectionEdit {
  index: number;
  label: string;
  start: number;
  end: number;
  originalLabel: string;
}

interface ChordEdit {
  index: number;
  label: string;
  originalLabel: string;
  start: number;
  changed: boolean;
}

function buildChordLabel(root: string, quality: string): string {
  const qualityDisplay: Record<string, string> = {
    maj: "", min: "m", dim: "dim", aug: "aug",
    maj7: "maj7", min7: "m7", "7": "7", dim7: "dim7",
    hdim7: "ø7", sus2: "sus2", sus4: "sus4", add9: "add9",
  };
  return `${root}${qualityDisplay[quality] ?? quality}`;
}

function parseChordLabel(label: string): { root: string; quality: string } {
  const roots = ["C#", "Db", "D#", "Eb", "F#", "Gb", "G#", "Ab", "A#", "Bb", "C", "D", "E", "F", "G", "A", "B", "N"];
  for (const root of roots) {
    if (label.startsWith(root)) {
      const rest = label.slice(root.length);
      const quality = rest === "m" ? "min" : rest === "" ? "maj" : rest;
      return { root, quality };
    }
  }
  return { root: label, quality: "maj" };
}

export function CorrectionsDrawer({ analysis, projectId, onClose, onSaved }: CorrectionsDrawerProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>("global");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  // ── Global state ────────────────────────────────────────────────────────────
  const [bpm, setBpm] = useState<string>(
    analysis?.rhythm?.bpm ? String(Math.round(analysis.rhythm.bpm)) : ""
  );
  const [globalKey, setGlobalKey] = useState<string>(analysis?.key?.globalKey || "");
  const [mode, setMode] = useState<string>(analysis?.key?.mode || "major");

  // ── Section state ───────────────────────────────────────────────────────────
  const rawSections: any[] = analysis?.structure?.sections ?? [];
  const [sectionEdits, setSectionEdits] = useState<SectionEdit[]>(() =>
    rawSections.map((s: any, i: number) => ({
      index: i,
      label: s.label ?? s.name ?? "",
      start: s.start ?? s.startTime ?? 0,
      end: s.end ?? s.endTime ?? (s.start ?? 0) + (s.duration ?? 0),
      originalLabel: s.label ?? s.name ?? "",
    }))
  );

  const updateSectionLabel = useCallback((i: number, label: string) => {
    setSectionEdits(prev => prev.map(s => s.index === i ? { ...s, label } : s));
  }, []);

  const updateSectionTime = useCallback((i: number, field: "start" | "end", val: string) => {
    const num = parseFloat(val);
    if (isNaN(num)) return;
    setSectionEdits(prev => prev.map(s => s.index === i ? { ...s, [field]: num } : s));
  }, []);

  // ── Chord state ─────────────────────────────────────────────────────────────
  const rawChords: any[] = analysis?.chords?.chords ?? [];
  const [chordEdits, setChordEdits] = useState<ChordEdit[]>(() =>
    rawChords.map((c: any, i: number) => {
      const label = c.label ?? c.chord ?? "N";
      return {
        index: i,
        label,
        originalLabel: label,
        start: c.start ?? c.startTime ?? 0,
        changed: false,
      };
    })
  );

  const updateChordLabel = useCallback((i: number, label: string) => {
    setChordEdits(prev => prev.map(c =>
      c.index === i ? { ...c, label, changed: label !== c.originalLabel } : c
    ));
  }, []);

  const resetChord = useCallback((i: number) => {
    setChordEdits(prev => prev.map(c =>
      c.index === i ? { ...c, label: c.originalLabel, changed: false } : c
    ));
  }, []);

  // ── Submit ───────────────────────────────────────────────────────────────────
  const handleSave = async () => {
    setSaving(true);
    try {
      const body: Record<string, unknown> = {};
      if (bpm) body.bpm = Number(bpm);
      if (globalKey) body.globalKey = globalKey;
      body.mode = mode;

      // Section corrections: only send modified ones
      const changedSections = sectionEdits.filter(s => {
        const orig = rawSections[s.index];
        return (
          s.label !== (orig?.label ?? orig?.name ?? "") ||
          Math.abs(s.start - (orig?.start ?? orig?.startTime ?? 0)) > 0.01 ||
          Math.abs(s.end   - (orig?.end   ?? orig?.endTime   ?? 0)) > 0.01
        );
      });
      if (changedSections.length > 0) {
        body.sections = changedSections.map(s => ({
          index: s.index,
          label: s.label,
          start: s.start,
          end:   s.end,
        }));
      }

      // Chord corrections: only send changed ones
      const changedChords = chordEdits.filter(c => c.changed);
      if (changedChords.length > 0) {
        body.chordOverrides = changedChords.map(c => ({ index: c.index, label: c.label }));
      }

      const res = await fetch(`/api/projects/${projectId}/corrections`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();

      // Invalidate analysis cache so the UI refreshes
      queryClient.invalidateQueries({ queryKey: [`/api/projects/${projectId}/analysis`] });

      setSaved(true);
      setTimeout(() => {
        onSaved(data.dependentStages ?? []);
        onClose();
      }, 900);
    } finally {
      setSaving(false);
    }
  };

  const tabs: { id: Tab; label: string; icon: React.ReactNode }[] = [
    { id: "global",   label: t("Global"),   icon: <Music2 className="w-3.5 h-3.5" /> },
    { id: "sections", label: t("Sections"), icon: <Layers className="w-3.5 h-3.5" /> },
    { id: "chords",   label: t("Chords"),   icon: <Edit3 className="w-3.5 h-3.5" /> },
  ];

  const changedChordsCount = chordEdits.filter(c => c.changed).length;
  const changedSectionsCount = sectionEdits.filter((s, i) => {
    const orig = rawSections[i];
    return s.label !== (orig?.label ?? orig?.name ?? "");
  }).length;

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/70 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg bg-card border border-white/10 rounded-t-2xl sm:rounded-2xl shadow-2xl flex flex-col max-h-[85vh]"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 pt-5 pb-0 shrink-0">
          <h3 className="font-display font-bold text-white flex items-center gap-2 text-sm">
            <Edit3 className="w-4 h-4 text-accent" /> {t("Manual Corrections")}
          </h3>
          <button onClick={onClose} className="text-muted-foreground hover:text-white transition-colors">
            <XCircle className="w-5 h-5" />
          </button>
        </div>

        <p className="px-6 pt-2 pb-3 text-xs text-muted-foreground shrink-0">
          {t("Corrections are applied immediately to the analysis. Regenerate your arrangement to hear the changes.")}
        </p>

        {/* Tabs */}
        <div className="flex border-b border-white/10 px-4 shrink-0">
          {tabs.map(({ id, label, icon }) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={cn(
                "flex items-center gap-1.5 px-4 py-2.5 text-xs font-medium transition-colors border-b-2 -mb-px relative",
                tab === id
                  ? "border-primary text-primary"
                  : "border-transparent text-muted-foreground hover:text-white"
              )}
            >
              {icon} {label}
              {id === "chords" && changedChordsCount > 0 && (
                <span className="ml-1 px-1.5 py-0.5 rounded-full bg-accent/20 text-accent text-[9px] font-bold">{changedChordsCount}</span>
              )}
              {id === "sections" && changedSectionsCount > 0 && (
                <span className="ml-1 px-1.5 py-0.5 rounded-full bg-accent/20 text-accent text-[9px] font-bold">{changedSectionsCount}</span>
              )}
            </button>
          ))}
        </div>

        {/* Tab Content */}
        <div className="flex-1 overflow-y-auto custom-scrollbar">

          {/* ── Global Tab ── */}
          {tab === "global" && (
            <div className="p-5 space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-xs uppercase tracking-wider text-muted-foreground">{t("BPM")}</label>
                  <input
                    type="number" min={20} max={300}
                    value={bpm}
                    onChange={e => setBpm(e.target.value)}
                    className="w-full bg-black/40 border border-white/10 rounded px-3 py-2 text-white text-sm focus:border-primary/60 outline-none"
                    placeholder="e.g. 120"
                    dir="ltr"
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs uppercase tracking-wider text-muted-foreground">{t("Key")}</label>
                  <select
                    value={globalKey}
                    onChange={e => setGlobalKey(e.target.value)}
                    className="w-full bg-black/40 border border-white/10 rounded px-3 py-2 text-white text-sm focus:border-primary/60 outline-none"
                    dir="ltr"
                  >
                    <option value="">{t("Auto")}</option>
                    {KEYS.map(k => <option key={k} value={k}>{k}</option>)}
                  </select>
                </div>
                <div className="space-y-1.5 col-span-2">
                  <label className="text-xs uppercase tracking-wider text-muted-foreground">{t("Mode / Scale")}</label>
                  <div className="flex flex-wrap gap-2">
                    {MODES.map(m => (
                      <button
                        key={m}
                        onClick={() => setMode(m)}
                        className={cn(
                          "px-3 py-1 rounded-full text-xs border transition-colors",
                          mode === m
                            ? "border-accent text-accent bg-accent/15"
                            : "border-white/10 text-muted-foreground hover:border-white/30"
                        )}
                      >
                        {m}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ── Sections Tab ── */}
          {tab === "sections" && (
            <div className="p-5 space-y-2">
              {sectionEdits.length === 0 ? (
                <p className="text-xs text-muted-foreground text-center py-8">{t("No sections detected yet")}</p>
              ) : (
                sectionEdits.map((sec, i) => {
                  const orig = rawSections[i];
                  const isChanged = sec.label !== (orig?.label ?? orig?.name ?? "");
                  return (
                    <div key={i} className={cn(
                      "rounded-lg border p-3 space-y-2 transition-colors",
                      isChanged ? "border-accent/40 bg-accent/5" : "border-white/8 bg-white/3"
                    )}>
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] text-muted-foreground font-mono w-6">{i + 1}.</span>
                        <input
                          value={sec.label}
                          onChange={e => updateSectionLabel(i, e.target.value)}
                          className="flex-1 bg-black/30 border border-white/10 rounded px-2 py-1 text-white text-sm focus:border-primary/50 outline-none"
                          placeholder={t("Section name")}
                          dir="rtl"
                        />
                        {isChanged && (
                          <button
                            onClick={() => updateSectionLabel(i, orig?.label ?? orig?.name ?? "")}
                            className="text-muted-foreground hover:text-white transition-colors"
                            title={t("Reset")}
                          >
                            <RotateCcw className="w-3.5 h-3.5" />
                          </button>
                        )}
                      </div>
                      <div className="flex gap-2 items-center text-[10px] text-muted-foreground" dir="ltr">
                        <span>{t("Start")}:</span>
                        <input
                          type="number" step="0.1"
                          value={sec.start.toFixed(1)}
                          onChange={e => updateSectionTime(i, "start", e.target.value)}
                          className="w-16 bg-black/20 border border-white/8 rounded px-1.5 py-0.5 text-white text-[11px] outline-none focus:border-primary/50"
                        />
                        <span>s</span>
                        <span className="ml-2">{t("End")}:</span>
                        <input
                          type="number" step="0.1"
                          value={sec.end.toFixed(1)}
                          onChange={e => updateSectionTime(i, "end", e.target.value)}
                          className="w-16 bg-black/20 border border-white/8 rounded px-1.5 py-0.5 text-white text-[11px] outline-none focus:border-primary/50"
                        />
                        <span>s</span>
                        <span className="ml-auto opacity-50 font-mono">
                          {((sec.end - sec.start)).toFixed(0)}s
                        </span>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          )}

          {/* ── Chords Tab ── */}
          {tab === "chords" && (
            <div className="p-5 space-y-1.5">
              {chordEdits.length === 0 ? (
                <p className="text-xs text-muted-foreground text-center py-8">{t("No chords detected yet")}</p>
              ) : (
                <>
                  <p className="text-[10px] text-muted-foreground pb-2">
                    {t("Click a chord label to edit. Changed chords are highlighted.")}
                  </p>
                  {chordEdits.map((chord, i) => {
                    const { root, quality } = parseChordLabel(chord.label);
                    return (
                      <div key={i} className={cn(
                        "flex items-center gap-2 rounded px-2 py-1.5 transition-colors border",
                        chord.changed ? "border-accent/40 bg-accent/5" : "border-transparent hover:border-white/8"
                      )}>
                        <span className="text-[9px] text-muted-foreground font-mono w-10 text-right shrink-0" dir="ltr">
                          {chord.start.toFixed(1)}s
                        </span>

                        {/* Root */}
                        <select
                          value={root}
                          onChange={e => updateChordLabel(i, buildChordLabel(e.target.value, quality))}
                          className="bg-black/30 border border-white/10 rounded px-1.5 py-0.5 text-white text-xs outline-none focus:border-primary/50 w-14"
                          dir="ltr"
                        >
                          {KEYS.map(k => <option key={k} value={k}>{k}</option>)}
                          <option value="N">N/A</option>
                        </select>

                        {/* Quality */}
                        <select
                          value={quality}
                          onChange={e => updateChordLabel(i, buildChordLabel(root, e.target.value))}
                          className="bg-black/30 border border-white/10 rounded px-1.5 py-0.5 text-white text-xs outline-none focus:border-primary/50 flex-1"
                          dir="ltr"
                        >
                          {CHORD_QUALITIES.map(q => (
                            <option key={q} value={q}>{q}</option>
                          ))}
                        </select>

                        {/* Preview */}
                        <span className={cn(
                          "text-xs font-bold w-14 text-center font-mono",
                          chord.changed ? "text-accent" : "text-white/60"
                        )} dir="ltr">
                          {chord.label}
                        </span>

                        {chord.changed && (
                          <button
                            onClick={() => resetChord(i)}
                            className="text-muted-foreground hover:text-white transition-colors shrink-0"
                            title={t("Reset")}
                          >
                            <RotateCcw className="w-3 h-3" />
                          </button>
                        )}
                      </div>
                    );
                  })}
                </>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-4 border-t border-white/8 flex gap-3 shrink-0">
          <Button variant="outline" className="flex-1" onClick={onClose} disabled={saving}>
            {t("Cancel")}
          </Button>
          <Button variant="glow" className="flex-1" onClick={handleSave} disabled={saving || saved}>
            {saved
              ? <><CheckCircle2 className="w-4 h-4 mr-1.5" />{t("Saved!")}</>
              : saving
                ? <><Loader2 className="w-4 h-4 mr-1.5 animate-spin" />{t("Saving...")}</>
                : t("Apply Corrections")
            }
          </Button>
        </div>
      </div>
    </div>
  );
}
