import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Edit3, XCircle, CheckCircle2, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface CorrectionsDrawerProps {
  analysis: any;
  projectId: number;
  onClose: () => void;
  onSaved: () => void;
}

const KEYS = ["C", "C#", "Db", "D", "D#", "Eb", "E", "F", "F#", "Gb", "G", "G#", "Ab", "A", "A#", "Bb", "B"];
const MODES = ["major", "minor", "dorian", "phrygian", "lydian", "mixolydian", "aeolian", "locrian"];

export function CorrectionsDrawer({ analysis, projectId, onClose, onSaved }: CorrectionsDrawerProps) {
  const { t } = useTranslation();
  const [bpm, setBpm] = useState<string>(analysis?.rhythm?.bpm ? String(Math.round(analysis.rhythm.bpm)) : "");
  const [globalKey, setGlobalKey] = useState<string>(analysis?.key?.globalKey || "");
  const [mode, setMode] = useState<string>(analysis?.key?.mode || "major");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      await fetch(`/api/projects/${projectId}/corrections`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          bpm: bpm ? Number(bpm) : undefined,
          globalKey: globalKey || undefined,
          mode: mode || undefined,
        }),
      });
      setSaved(true);
      setTimeout(() => { onSaved(); onClose(); }, 800);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/70 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md bg-card border border-white/10 rounded-t-2xl sm:rounded-2xl p-6 shadow-2xl space-y-5"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h3 className="font-display font-bold text-white flex items-center gap-2">
            <Edit3 className="w-4 h-4 text-accent" /> {t("Manual Corrections")}
          </h3>
          <button onClick={onClose} className="text-muted-foreground hover:text-white">
            <XCircle className="w-5 h-5" />
          </button>
        </div>

        <p className="text-xs text-muted-foreground">
          {t("Override AI analysis results. Corrections apply to subsequent arrangement generation.")}
        </p>

        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-1">
            <label className="text-xs uppercase tracking-wider text-muted-foreground">{t("BPM")}</label>
            <input
              type="number"
              min={20} max={300}
              value={bpm}
              onChange={e => setBpm(e.target.value)}
              className="w-full bg-black/40 border border-white/10 rounded px-3 py-2 text-white text-sm focus:border-primary/60 outline-none"
              placeholder="e.g. 120"
              dir="ltr"
            />
          </div>

          <div className="space-y-1">
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

          <div className="space-y-1 col-span-2">
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

        <div className="flex gap-3">
          <Button variant="outline" className="flex-1" onClick={onClose} disabled={saving}>
            {t("Cancel")}
          </Button>
          <Button variant="glow" className="flex-1" onClick={handleSave} disabled={saving || saved}>
            {saved
              ? <><CheckCircle2 className="w-4 h-4 mr-2" />{t("Saved!")}</>
              : saving
                ? <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                : t("Apply Corrections")
            }
          </Button>
        </div>
      </div>
    </div>
  );
}
