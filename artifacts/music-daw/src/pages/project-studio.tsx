import { useParams } from "wouter";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { JobProgress } from "@/components/job-progress";
import { PianoRoll } from "@/components/piano-roll";
import { AnalysisInspector } from "@/components/analysis-inspector";
import ExportCenter from "@/pages/export-center";
import ChatAgent from "@/components/chat-agent";
import { WaveformPlayer } from "@/components/waveform-player";
import { Button } from "@/components/ui/button";
import { Upload, Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";

import { useProjectStudio } from "@/hooks/use-project-studio";
import { TransportBar } from "@/components/studio/TransportBar";
import { MockBanner, FailedBanner } from "@/components/studio/Banners";
import { TrackLane } from "@/components/studio/TrackLane";
import { CorrectionsDrawer } from "@/components/studio/CorrectionsDrawer";
import { AnalysisTab } from "@/components/studio/AnalysisTab";
import { ArrangeTab } from "@/components/studio/ArrangeTab";

export default function ProjectStudio() {
  const { t } = useTranslation();
  const params = useParams();
  const projectId = parseInt(params.id || "0", 10);

  const studio = useProjectStudio(projectId);
  const fileInputRef = studio.fileInputRef;

  if (studio.isProjLoading) {
    return (
      <div className="h-screen flex items-center justify-center bg-background">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
      </div>
    );
  }
  if (!studio.project) {
    return <div className="p-8 text-center text-white">{t("Project not found")}</div>;
  }

  return (
    <div className="h-screen flex flex-col bg-background overflow-hidden selection:bg-primary/30 text-foreground">

      {/* ── Banners ── */}
      {studio.showMockBanner && <MockBanner onDismiss={() => studio.setShowMockBanner(false)} />}
      {studio.jobFailedMsg && <FailedBanner message={studio.jobFailedMsg} />}

      <JobProgress job={studio.activeJob} />

      <TransportBar project={studio.project} analysis={studio.analysis} />

      <div className="flex-1 flex overflow-hidden">

        {/* ── Main Editor (timeline + tracks) ── */}
        <div className="flex-1 flex flex-col min-w-0 bg-[#060608]">

          {/* Timeline: chord + section labels */}
          <div className="h-20 bg-card border-b border-white/5 flex flex-col justify-end px-4 relative overflow-hidden" dir="ltr">
            {studio.analysis?.structure?.sections?.map((sec: any, i: number) => (
              <div
                key={i}
                className="absolute top-0 h-6 border-l border-white/20 px-2 text-[10px] font-bold tracking-widest text-white/50 uppercase"
                style={{ left: `${sec.startTime * 20}px`, width: `${(sec.endTime - sec.startTime) * 20}px` }}
              >
                <div className="absolute inset-0 bg-accent/10 opacity-50" />
                {t(sec.label)}
              </div>
            ))}
            <div className="flex h-8 items-end gap-1 relative z-10 bottom-2">
              {studio.analysis?.chords?.chords?.slice(0, 30).map((chord: any, i: number) => (
                <div
                  key={i}
                  className="bg-primary/20 text-primary border border-primary/30 px-2 py-0.5 rounded text-xs font-medium shadow-[0_0_10px_rgba(0,240,255,0.1)] whitespace-nowrap"
                  style={{ position: "absolute", left: `${chord.startTime * 20}px` }}
                >
                  {chord.chord}
                </div>
              ))}
            </div>
          </div>

          {/* Tracks area */}
          <div className="flex-1 overflow-y-auto overflow-x-hidden relative">
            {!studio.project.audioFileName && !studio.arrangement ? (
              <div className="absolute inset-0 flex flex-col items-center justify-center text-center p-8">
                <div className="w-24 h-24 rounded-full bg-white/5 flex items-center justify-center mb-6 border border-white/10 border-dashed">
                  <Upload className="w-10 h-10 text-muted-foreground" />
                </div>
                <h3 className="text-xl font-display font-semibold mb-2">{t("Drop Audio File to Analyze")}</h3>
                <p className="text-muted-foreground max-w-md mb-6">{t("Upload a track to extract chords, BPM, stems, and structure. Or go straight to arrangement generation.")}</p>
                <Button variant="glow" onClick={() => fileInputRef.current?.click()}>
                  <Upload className="w-4 h-4 mr-2" /> {t("Upload Audio")}
                </Button>
              </div>
            ) : (
              <div className="w-full">
                {studio.project.audioFileName && (
                  <div className="flex border-b border-white/10 h-32 group">
                    <div className="w-64 bg-card border-r border-white/10 flex items-center px-4">
                      <span className="font-medium text-sm text-white">{t("Original Audio")}</span>
                    </div>
                    <div className="flex-1 bg-[#0a0a0c] relative px-2 py-1">
                      {studio.analysis?.waveformData ? (
                        <WaveformPlayer
                          audioUrl={studio.project.audioFileName ? `/api/projects/${projectId}/audio` : undefined}
                          peaks={studio.analysis.waveformData}
                          duration={studio.analysis.duration ?? studio.project.audioDurationSeconds}
                        />
                      ) : (
                        <div className="absolute inset-0 flex items-center justify-center">
                          {studio.activeJobId
                            ? <Loader2 className="w-6 h-6 animate-spin text-primary" />
                            : <Button size="sm" variant="outline" onClick={studio.handleAnalyze}>{t("Analyze Audio")}</Button>
                          }
                        </div>
                      )}
                    </div>
                  </div>
                )}
                {studio.arrangement?.tracks?.map((track: any) => (
                  <TrackLane
                    key={track.id}
                    track={track}
                    isSelected={studio.selectedTrack?.id === track.id}
                    onSelect={() => studio.setSelectedTrack((prev: any) => prev?.id === track.id ? null : track)}
                    onRegen={studio.arrangement ? studio.handleRegenTrack : undefined}
                  />
                ))}
              </div>
            )}
          </div>
        </div>

        {/* ── Right Panel (tabs) ── */}
        <div className="w-[340px] border-l border-white/10 bg-card flex flex-col z-20 shadow-2xl relative">
          <Tabs value={studio.activeTab} onValueChange={studio.setActiveTab} className="flex-1 flex flex-col">

            <div className="p-4 border-b border-white/5">
              <TabsList className="w-full grid grid-cols-5 text-[11px]">
                <TabsTrigger value="analysis">{t("Analyze")}</TabsTrigger>
                <TabsTrigger value="inspect">{t("Inspect")}</TabsTrigger>
                <TabsTrigger value="arrange">{t("Arrange")}</TabsTrigger>
                <TabsTrigger value="agent">{t("agent.tab")}</TabsTrigger>
                <TabsTrigger value="export">{t("Export")}</TabsTrigger>
              </TabsList>
            </div>

            <div className="flex-1 overflow-y-auto p-4 custom-scrollbar">

              {/* Analysis Tab */}
              <TabsContent value="analysis" className="space-y-6 mt-0">
                <AnalysisTab
                  analysis={studio.analysis}
                  project={studio.project}
                  projectId={projectId}
                  activeJobId={studio.activeJobId}
                  isMockMode={studio.isMockMode}
                  modelVersions={studio.modelVersions}
                  lockedFields={studio.lockedFields}
                  chordOverrides={studio.chordOverrides}
                  editingChordIdx={studio.editingChordIdx}
                  onAnalyze={studio.handleAnalyze}
                  onUploadClick={() => fileInputRef.current?.click()}
                  onToggleLock={studio.toggleLock}
                  onSetChordOverride={studio.handleSetChordOverride}
                  onSetEditingChordIdx={studio.setEditingChordIdx}
                />
              </TabsContent>

              {/* Inspect Tab */}
              <TabsContent value="inspect" className="mt-0">
                <AnalysisInspector analysis={studio.analysis} />
              </TabsContent>

              {/* Arrange Tab */}
              <TabsContent value="arrange" className="space-y-4 mt-0">
                <ArrangeTab
                  arrangement={studio.arrangement}
                  styles={studio.styles ?? []}
                  personas={studio.personas}
                  selectedStyle={studio.selectedStyle}
                  selectedPersona={studio.selectedPersona}
                  activeJobId={studio.activeJobId}
                  onSelectStyle={studio.setSelectedStyle}
                  onSelectPersona={studio.setSelectedPersona}
                  onArrange={studio.handleArrange}
                />
              </TabsContent>

              {/* Agent Tab */}
              <TabsContent value="agent" className="mt-0 h-[calc(100vh-200px)] min-h-[400px]">
                <ChatAgent
                  projectId={projectId}
                  onProfileReady={(profile) => { console.log("[ChatAgent] Profile confirmed:", profile); }}
                  className="h-full"
                />
              </TabsContent>

              {/* Export Tab */}
              <TabsContent value="export" className="mt-0">
                <ExportCenter projectId={projectId} hasArrangement={!!studio.arrangement} />
              </TabsContent>

            </div>
          </Tabs>
        </div>
      </div>

      {/* Piano Roll */}
      {studio.selectedTrack && (
        <PianoRoll
          track={studio.selectedTrack}
          bpm={studio.analysis?.rhythm?.bpm ?? 120}
          totalDurationSeconds={studio.project?.audioDurationSec ?? 180}
          onClose={() => studio.setSelectedTrack(null)}
        />
      )}

      {/* Manual Corrections Modal */}
      {studio.showCorrections && (
        <CorrectionsDrawer
          analysis={studio.analysis}
          projectId={projectId}
          onClose={() => studio.setShowCorrections(false)}
          onSaved={() => {
            studio.invalidateAll();
            studio.setShowCorrections(false);
          }}
        />
      )}

      {/* Hidden file input */}
      <input type="file" ref={fileInputRef} className="hidden" accept="audio/*" onChange={studio.handleUpload} />
    </div>
  );
}
