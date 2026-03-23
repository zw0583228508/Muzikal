import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { MidiPlayer } from "@/components/midi-player";
import { Music, CheckCircle2, Layers } from "lucide-react";
import { cn } from "@/lib/utils";

interface ArrangeTabProps {
  arrangement: any;
  styles: any[];
  personas: any[];
  selectedStyle: string;
  selectedPersona: string | null;
  activeJobId: string | null;
  onSelectStyle: (styleId: string) => void;
  onSelectPersona: (personaId: string | null) => void;
  onArrange: () => void;
}

export function ArrangeTab({
  arrangement,
  styles,
  personas,
  selectedStyle,
  selectedPersona,
  activeJobId,
  onSelectStyle,
  onSelectPersona,
  onArrange,
}: ArrangeTabProps) {
  const { t } = useTranslation();

  return (
    <>
      {/* Style Picker */}
      <div className="daw-panel p-4">
        <h4 className="text-xs font-display font-bold text-muted-foreground uppercase tracking-widest mb-4">{t("Style")}</h4>
        <div className="grid grid-cols-2 gap-2 max-h-72 overflow-y-auto custom-scrollbar pr-1">
          {styles?.map((style: any) => (
            <button
              key={style.id}
              onClick={() => onSelectStyle(style.id)}
              className={cn(
                "p-3 text-left rounded border transition-all ltr:text-left rtl:text-right",
                selectedStyle === style.id
                  ? "border-primary/70 bg-primary/20 shadow-[0_0_12px_rgba(0,240,255,0.2)]"
                  : "border-white/10 bg-white/5 hover:bg-primary/10 hover:border-primary/30"
              )}
            >
              <div className={cn("text-sm font-bold", selectedStyle === style.id ? "text-primary" : "text-white")}>
                {t(style.name)}
              </div>
              <div className="text-[10px] text-muted-foreground">{t(style.genre)}</div>
            </button>
          ))}
        </div>
      </div>

      {/* Persona Picker */}
      {personas.length > 0 && (
        <div className="daw-panel p-4">
          <div className="flex items-center justify-between mb-3">
            <h4 className="text-xs font-display font-bold text-muted-foreground uppercase tracking-widest">{t("Persona")}</h4>
            {selectedPersona && (
              <button
                onClick={() => onSelectPersona(null)}
                className="text-[10px] text-muted-foreground hover:text-white transition-colors"
              >
                {t("ביטול")}
              </button>
            )}
          </div>
          <div className="grid grid-cols-2 gap-2 max-h-56 overflow-y-auto custom-scrollbar pr-1">
            {personas.map((persona: any) => (
              <button
                key={persona.id}
                onClick={() => onSelectPersona(selectedPersona === persona.id ? null : persona.id)}
                className={cn(
                  "p-2.5 text-right rounded border transition-all text-xs",
                  selectedPersona === persona.id
                    ? "border-accent/70 bg-accent/15 shadow-[0_0_10px_rgba(255,160,80,0.15)]"
                    : "border-white/10 bg-white/5 hover:bg-accent/10 hover:border-accent/30"
                )}
              >
                <div className={cn("font-bold text-[11px] truncate", selectedPersona === persona.id ? "text-accent" : "text-white")}>
                  {persona.name}
                </div>
                <div className="text-[9px] text-muted-foreground truncate">{persona.nameEn}</div>
                {persona.tags?.length > 0 && (
                  <div className="flex gap-0.5 mt-1 flex-wrap">
                    {persona.tags.slice(0, 2).map((tag: string) => (
                      <span key={tag} className="px-1 py-0 rounded-full bg-white/5 text-[8px] text-muted-foreground">{tag}</span>
                    ))}
                  </div>
                )}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Density + Tempo */}
      <div className="daw-panel p-4 space-y-4">
        <div>
          <div className="flex justify-between mb-2">
            <h4 className="text-xs font-display font-bold text-muted-foreground uppercase tracking-widest">{t("Density")}</h4>
            <span className="text-xs text-primary" dir="ltr">80%</span>
          </div>
          <Slider defaultValue={[80]} max={100} dir="ltr" />
        </div>
        <div>
          <div className="flex justify-between mb-2">
            <h4 className="text-xs font-display font-bold text-muted-foreground uppercase tracking-widest">{t("Tempo Factor")}</h4>
            <span className="text-xs text-white" dir="ltr">1.0x</span>
          </div>
          <Slider defaultValue={[50]} max={100} dir="ltr" />
        </div>
      </div>

      {/* MIDI Preview */}
      {arrangement?.tracks?.length > 0 && (
        <div className="daw-panel p-4 space-y-3">
          <div className="flex items-center gap-2 mb-1">
            <Music className="w-3.5 h-3.5 text-primary/70" />
            <h4 className="text-xs font-display font-bold text-muted-foreground uppercase tracking-widest">{t("MIDI Preview")}</h4>
          </div>
          <MidiPlayer
            tracks={arrangement.tracks.map((tr: any) => ({
              id: tr.id ?? String(tr.instrument),
              instrument: tr.instrument,
              midiProgram: tr.midiProgram,
              notes: tr.notes ?? [],
              volume: 80,
            }))}
            totalDuration={arrangement.totalDuration ?? arrangement.durationSeconds}
          />
        </div>
      )}

      {/* Harmonic Plan */}
      {arrangement?.arrangementPlan?.harmonicPlan && (
        <div className="daw-panel p-4 space-y-2">
          <h4 className="text-xs font-display font-bold text-muted-foreground uppercase tracking-widest">{t("Harmonic Plan")}</h4>
          <p className="text-xs font-mono text-white/70 leading-relaxed" dir="ltr">
            {Array.isArray(arrangement.arrangementPlan.harmonicPlan)
              ? arrangement.arrangementPlan.harmonicPlan.join(" → ")
              : String(arrangement.arrangementPlan.harmonicPlan)}
          </p>
          {arrangement.arrangementPlan.profileUsed && (
            <p className="text-[10px] text-muted-foreground">
              {t("Profile")}: <span className="text-primary/80">{arrangement.arrangementPlan.profileUsed}</span>
            </p>
          )}
        </div>
      )}

      {/* Transitions */}
      {(() => {
        const transitions = (arrangement as any)?.generationMetadata?.transitions ?? (arrangement as any)?.transitions;
        if (!transitions?.length) return null;
        return (
          <div className="daw-panel p-4 space-y-2">
            <h4 className="text-xs font-display font-bold text-muted-foreground uppercase tracking-widest">{t("Transitions")}</h4>
            <div className="space-y-1" dir="ltr">
              {transitions.map((tr: any, i: number) => (
                <div key={i} className="flex items-center gap-2 text-xs">
                  <span className="text-white/60 capitalize">{tr.fromSection}</span>
                  <span className="text-primary/60">→</span>
                  <span className="text-white/60 capitalize">{tr.toSection}</span>
                  <span className="ml-auto text-accent/60 font-mono bg-accent/10 px-1.5 py-0.5 rounded text-[9px]">{tr.type}</span>
                </div>
              ))}
            </div>
          </div>
        );
      })()}

      {/* Instrumentation */}
      {(() => {
        const plan = (arrangement as any)?.generationMetadata?.instrumentationPlan ?? (arrangement as any)?.instrumentationPlan;
        if (!plan?.tracks?.length) return null;
        return (
          <div className="daw-panel p-4 space-y-2">
            <h4 className="text-xs font-display font-bold text-muted-foreground uppercase tracking-widest">{t("Instrumentation")}</h4>
            <div className="space-y-1" dir="ltr">
              {plan.tracks.map((tr: any, i: number) => (
                <div key={i} className="flex items-center justify-between text-xs">
                  <span className="text-white/70 capitalize">{tr.instrument}</span>
                  <span className="text-muted-foreground">{tr.role}</span>
                  <div className="w-16 h-1.5 bg-white/5 rounded-full overflow-hidden">
                    <div className="h-full bg-primary/50 rounded-full" style={{ width: `${Math.round((tr.density ?? 0) * 100)}%` }} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        );
      })()}

      {/* Pinned Generate button */}
      <div className="sticky bottom-0 pb-1 bg-card pt-3 border-t border-white/5 space-y-2">
        {arrangement && (
          <p className="text-xs text-center text-green-400/80 flex items-center justify-center gap-1">
            <CheckCircle2 className="w-3 h-3" /> {t("Arrangement ready")} — {styles?.find((s: any) => s.id === arrangement.styleId)?.name}
          </p>
        )}
        <Button variant="glow" className="w-full" onClick={onArrange} disabled={!!activeJobId}>
          <Layers className="w-4 h-4 mr-2" /> {t("Generate Arrangement")}
        </Button>
      </div>
    </>
  );
}
