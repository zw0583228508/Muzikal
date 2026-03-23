import { Link } from "wouter";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { AudioPlayer } from "@/components/audio-player";
import { LanguageToggle } from "@/components/language-toggle";
import { ChevronLeft, AlertTriangle } from "lucide-react";

interface TransportBarProps {
  project: any;
  analysis: any;
}

export function TransportBar({ project, analysis }: TransportBarProps) {
  const { t } = useTranslation();
  const hasAudio = !!(project?.audioFilePath || project?.audioFileName);
  const isMock = !!(analysis?.isMock || analysis?.rhythm?.isMock);

  return (
    <div className="border-b border-white/10 bg-background/95 backdrop-blur sticky top-0 z-40">
      <div className="h-12 flex items-center px-4 justify-between">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" asChild className="ltr:rotate-0 rtl:rotate-180 h-8 w-8">
            <Link href="/"><ChevronLeft className="w-4 h-4" /></Link>
          </Button>
          <h2 className="font-display font-semibold text-base text-white/80 truncate max-w-[200px]">{project?.name}</h2>
          {isMock && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-500/20 border border-amber-500/40 text-amber-400 text-[10px] font-bold tracking-widest uppercase">
              <AlertTriangle className="w-3 h-3" />
              {t("MOCK")}
            </span>
          )}
        </div>

        <div className="flex items-center gap-5 text-xs font-display uppercase tracking-widest text-muted-foreground" dir="ltr">
          <div className="flex flex-col items-center">
            <span className="text-white font-bold text-sm">{analysis?.rhythm?.bpm ? Math.round(analysis.rhythm.bpm) : '—'}</span>
            <span className="text-[9px]">{t("BPM")}</span>
          </div>
          <div className="flex flex-col items-center">
            <span className="text-primary font-bold text-sm">{analysis?.rhythm?.timeSignatureNumerator || '4'}/{analysis?.rhythm?.timeSignatureDenominator || '4'}</span>
            <span className="text-[9px]">{t("TIME")}</span>
          </div>
          <div className="flex flex-col items-center">
            <span className="text-accent font-bold text-sm">
              {analysis?.key?.globalKey ? `${analysis.key.globalKey} ${analysis.key.mode || 'Maj'}` : '—'}
            </span>
            <span className="text-[9px]">{t("Key")}</span>
          </div>
          {analysis?.pipelineVersion && (
            <div className="flex flex-col items-center" title={t("Pipeline version")}>
              <span className="text-white/40 font-mono text-[9px]">v{analysis.pipelineVersion}</span>
              <span className="text-[9px]">{t("ENGINE")}</span>
            </div>
          )}
        </div>

        <div className="flex items-center gap-2">
          <LanguageToggle />
        </div>
      </div>

      <div className="px-4 pb-2">
        <AudioPlayer
          projectId={project?.id || 0}
          hasAudio={hasAudio}
          className="bg-black/30 rounded-lg px-3 py-2 border border-white/5"
        />
      </div>
    </div>
  );
}
