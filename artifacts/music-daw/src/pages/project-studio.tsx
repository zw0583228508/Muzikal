import { useState, useRef, useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams, Link } from "wouter";
import {
  useGetProject,
  useGetAnalysisResults,
  useGetArrangement,
  useUploadAudio,
  useStartAnalysis,
  useGenerateArrangement,
  useExportProject,
  useListStyles
} from "@workspace/api-client-react";
import { useJobPolling } from "@/hooks/use-job-polling";
import { useJobWebSocket, type JobUpdate } from "@/hooks/use-job-websocket";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { JobProgress } from "@/components/job-progress";
import {
  Play, Pause, Square, SkipBack, Search, Volume2, Settings2,
  ChevronLeft, Upload, Zap, Download, Layers, Activity, Music,
  Settings, Loader2, FileMusic, FileAudio, FileText, HardDrive,
  AlertTriangle, Edit3, CheckCircle2, XCircle
} from "lucide-react";
import { formatTime, cn } from "@/lib/utils";
import { useTranslation } from "react-i18next";
import { LanguageToggle } from "@/components/language-toggle";
import { AudioPlayer } from "@/components/audio-player";

// ─── Transport Bar ────────────────────────────────────────────────────────────

function TransportBar({ project, analysis }: { project: any; analysis: any }) {
  const { t } = useTranslation();
  const hasAudio = !!(project?.audioFilePath || project?.audioFileName);

  return (
    <div className="border-b border-white/10 bg-background/95 backdrop-blur sticky top-0 z-40">
      {/* Row 1: nav + metadata + language */}
      <div className="h-12 flex items-center px-4 justify-between">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" asChild className="ltr:rotate-0 rtl:rotate-180 h-8 w-8">
            <Link href="/"><ChevronLeft className="w-4 h-4" /></Link>
          </Button>
          <h2 className="font-display font-semibold text-base text-white/80 truncate max-w-[200px]">{project?.name}</h2>
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
            <span className="text-accent font-bold text-sm">{analysis?.key?.globalKey ? `${analysis.key.globalKey} ${analysis.key.mode || 'Maj'}` : '—'}</span>
            <span className="text-[9px]">{t("Key")}</span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <LanguageToggle />
        </div>
      </div>

      {/* Row 2: Audio player */}
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

// ─── Mock Mode Banner ─────────────────────────────────────────────────────────

function MockBanner({ onDismiss }: { onDismiss: () => void }) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-3 px-4 py-2 bg-amber-500/15 border-b border-amber-500/30 text-amber-400 text-xs">
      <AlertTriangle className="w-4 h-4 flex-shrink-0" />
      <span className="flex-1">
        <strong>{t("MOCK MODE")}</strong> — {t("Python audio backend unavailable. Results are simulated for UI testing only and do not reflect real analysis.")}
      </span>
      <button onClick={onDismiss} className="text-amber-400/60 hover:text-amber-400 ml-2">
        <XCircle className="w-4 h-4" />
      </button>
    </div>
  );
}

// ─── Job Failed Banner ────────────────────────────────────────────────────────

function FailedBanner({ message }: { message: string }) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-3 px-4 py-2 bg-red-500/15 border-b border-red-500/30 text-red-400 text-xs">
      <XCircle className="w-4 h-4 flex-shrink-0" />
      <span><strong>{t("Job Failed")}</strong> — {message}</span>
    </div>
  );
}

// ─── Track Lane ───────────────────────────────────────────────────────────────

function TrackLane({ track }: { track: any }) {
  const { t } = useTranslation();
  return (
    <div className="flex border-b border-white/5 h-24 group relative">
      <div className="w-64 bg-card border-r border-white/10 flex flex-col justify-center px-3 z-10">
        <div className="flex justify-between items-center mb-2">
          <span className="font-medium text-sm text-white truncate flex items-center gap-2">
            <div className="w-2 h-2 rounded-full" style={{ backgroundColor: track.color || '#00f0ff' }} />
            {t(track.name)}
          </span>
          <div className="flex gap-1" dir="ltr">
            <button className={cn("w-6 h-6 rounded text-xs font-bold transition-colors", track.muted ? "bg-accent/20 text-accent" : "bg-white/5 hover:bg-white/10")}>M</button>
            <button className={cn("w-6 h-6 rounded text-xs font-bold transition-colors", track.soloed ? "bg-yellow-500/20 text-yellow-500" : "bg-white/5 hover:bg-white/10")}>S</button>
          </div>
        </div>
        <div className="flex items-center gap-2" dir="ltr">
          <Volume2 className="w-3 h-3 text-muted-foreground" />
          <Slider defaultValue={[track.volume * 100]} max={100} className="w-full" />
        </div>
      </div>
      <div className="flex-1 bg-[#0a0a0c] relative overflow-hidden flex items-center px-4" dir="ltr">
        <div className="absolute inset-0 bg-[linear-gradient(90deg,rgba(255,255,255,0.02)_1px,transparent_1px)] bg-[size:2rem_100%]" />
        {track.notes?.slice(0, 60).map((note: any, i: number) => (
          <div
            key={i}
            className="absolute h-2 rounded-sm shadow-sm"
            style={{
              left: `${note.startTime * 20}px`,
              width: `${Math.max(note.duration * 20, 2)}px`,
              bottom: `${(note.pitch % 24) * 4}px`,
              backgroundColor: track.color || '#00f0ff',
              opacity: note.velocity / 127,
            }}
          />
        ))}
      </div>
    </div>
  );
}

// ─── Waveform ─────────────────────────────────────────────────────────────────

function WaveformVisualizer({ data }: { data?: number[] }) {
  const { t } = useTranslation();
  if (!data || data.length === 0) return <div className="h-32 flex items-center justify-center text-muted-foreground">{t("No waveform data")}</div>;
  const displayData = data.filter((_, i) => i % Math.ceil(data.length / 500) === 0).slice(0, 500);
  return (
    <div className="h-32 w-full flex items-end gap-[1px] px-4 opacity-70" dir="ltr">
      {displayData.map((val, i) => (
        <div
          key={i}
          className="bg-primary/60 flex-1 rounded-t-sm transition-all hover:bg-primary"
          style={{ height: `${Math.max(2, Math.abs(val) * 100)}%` }}
        />
      ))}
    </div>
  );
}

// ─── Manual Corrections Modal ─────────────────────────────────────────────────

function CorrectionsDrawer({
  analysis,
  projectId,
  onClose,
  onSaved,
}: {
  analysis: any;
  projectId: number;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useTranslation();
  const [bpm, setBpm] = useState<string>(analysis?.rhythm?.bpm ? String(Math.round(analysis.rhythm.bpm)) : "");
  const [globalKey, setGlobalKey] = useState<string>(analysis?.key?.globalKey || "");
  const [mode, setMode] = useState<string>(analysis?.key?.mode || "major");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const KEYS = ["C", "C#", "Db", "D", "D#", "Eb", "E", "F", "F#", "Gb", "G", "G#", "Ab", "A", "A#", "Bb", "B"];
  const MODES = ["major", "minor", "dorian", "phrygian", "lydian", "mixolydian", "aeolian", "locrian"];

  const handleSave = async () => {
    setSaving(true);
    try {
      await fetch(`/api/projects/${projectId}/corrections`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ bpm: bpm ? Number(bpm) : undefined, globalKey: globalKey || undefined, mode: mode || undefined }),
      });
      setSaved(true);
      setTimeout(() => { onSaved(); onClose(); }, 800);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/70 backdrop-blur-sm" onClick={onClose}>
      <div
        className="w-full max-w-md bg-card border border-white/10 rounded-t-2xl sm:rounded-2xl p-6 shadow-2xl space-y-5"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h3 className="font-display font-bold text-white flex items-center gap-2">
            <Edit3 className="w-4 h-4 text-accent" /> {t("Manual Corrections")}
          </h3>
          <button onClick={onClose} className="text-muted-foreground hover:text-white"><XCircle className="w-5 h-5" /></button>
        </div>

        <p className="text-xs text-muted-foreground">{t("Override AI analysis results. Corrections apply to subsequent arrangement generation.")}</p>

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
          <Button variant="outline" className="flex-1" onClick={onClose} disabled={saving}>{t("Cancel")}</Button>
          <Button variant="glow" className="flex-1" onClick={handleSave} disabled={saving || saved}>
            {saved ? <><CheckCircle2 className="w-4 h-4 mr-2" />{t("Saved!")}</> : saving ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : t("Apply Corrections")}
          </Button>
        </div>
      </div>
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function ProjectStudio() {
  const { t } = useTranslation();
  const params = useParams();
  const projectId = parseInt(params.id || "0", 10);
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [activeJobIsMock, setActiveJobIsMock] = useState(false);
  const [jobFailedMsg, setJobFailedMsg] = useState<string | null>(null);
  const [showMockBanner, setShowMockBanner] = useState(false);
  const [showCorrections, setShowCorrections] = useState(false);
  const [selectedStyle, setSelectedStyle] = useState("pop");
  const [selectedFormats, setSelectedFormats] = useState<Record<string, boolean>>({
    midi: true, musicxml: false, pdf: false,
    wav: true, flac: false, mp3: false, stems: false,
  });

  // ─ Data
  const { data: project, isLoading: isProjLoading } = useGetProject(projectId);
  const { data: analysis } = useGetAnalysisResults(projectId, { query: { retry: false } });
  const { data: arrangement } = useGetArrangement(projectId, { query: { retry: false } });
  const { data: styles } = useListStyles();
  const filesQueryKey = [`/api/projects/${projectId}/files`];
  const { data: projectFiles = [] } = useQuery<any[]>({
    queryKey: filesQueryKey,
    queryFn: () => fetch(`/api/projects/${projectId}/files`).then(r => r.json()),
    refetchInterval: 0,
  });

  // ─ Mutations
  const uploadMut = useUploadAudio();
  const analyzeMut = useStartAnalysis();
  const arrangeMut = useGenerateArrangement();
  const exportMut = useExportProject();

  // ─ Invalidate helper
  const invalidateAll = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: [`/api/projects/${projectId}`] });
    queryClient.invalidateQueries({ queryKey: [`/api/projects/${projectId}/analysis`] });
    queryClient.invalidateQueries({ queryKey: [`/api/projects/${projectId}/arrangement`] });
    queryClient.invalidateQueries({ queryKey: filesQueryKey });
  }, [queryClient, projectId]);

  // ─ Job completion handler
  const onJobComplete = useCallback(() => {
    invalidateAll();
    setActiveJobId(null);
    setJobFailedMsg(null);
  }, [invalidateAll]);

  // ─ WebSocket (real-time updates, primary mechanism)
  const { subscribeToJob } = useJobWebSocket({
    projectId,
    onJobUpdate: useCallback((update: JobUpdate) => {
      if (update.isMock) {
        setActiveJobIsMock(true);
        setShowMockBanner(true);
      }
      if (update.status === "completed") {
        onJobComplete();
      }
      if (update.status === "failed") {
        setJobFailedMsg(update.errorMessage || "Unknown error");
        setActiveJobId(null);
        setActiveJobIsMock(false);
      }
    }, [onJobComplete]),
  });

  // ─ Polling (fallback / backup)
  const { job: activeJob } = useJobPolling(activeJobId, onJobComplete);

  // ─ Job starter helper
  const startJob = useCallback((jobId: string) => {
    setActiveJobId(jobId);
    setActiveJobIsMock(false);
    setJobFailedMsg(null);
    subscribeToJob(jobId);
  }, [subscribeToJob]);

  // ─ Handlers
  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const res = await uploadMut.mutateAsync({ projectId, data: { file } });
      startJob(res.jobId);
      invalidateAll();
    } catch (err) {
      console.error(err);
      alert(t("Upload failed"));
    }
  };

  const handleAnalyze = async () => {
    try {
      const res = await analyzeMut.mutateAsync({ projectId });
      startJob(res.jobId);
    } catch (err) {
      console.error(err);
      alert(t("Analysis failed to start"));
    }
  };

  const handleArrange = async () => {
    try {
      const res = await arrangeMut.mutateAsync({
        projectId,
        data: { styleId: selectedStyle, density: 0.8, humanize: true }
      });
      startJob(res.jobId);
    } catch (err) {
      console.error(err);
    }
  };

  const handleExport = () => {
    const formats = ["midi", "musicxml", "pdf"].filter(f => selectedFormats[f]);
    if (!formats.length) return;
    exportMut.mutate({ projectId, data: { formats } }, {
      onSuccess: (res: any) => startJob(res.jobId),
    });
  };

  const handleRender = async () => {
    const formats = ["wav", "flac", "mp3", "stems"].filter(f => selectedFormats[f]);
    if (!formats.length) return;
    try {
      const res = await fetch(`/api/projects/${projectId}/render`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ formats }),
      });
      const data = await res.json();
      startJob(data.jobId);
    } catch (e) { console.error(e); }
  };

  if (isProjLoading) return <div className="h-screen flex items-center justify-center bg-background"><Loader2 className="w-8 h-8 animate-spin text-primary" /></div>;
  if (!project) return <div className="p-8 text-center text-white">{t("Project not found")}</div>;

  return (
    <div className="h-screen flex flex-col bg-background overflow-hidden selection:bg-primary/30 text-foreground">
      {/* Banners */}
      {showMockBanner && <MockBanner onDismiss={() => setShowMockBanner(false)} />}
      {jobFailedMsg && <FailedBanner message={jobFailedMsg} />}

      <JobProgress job={activeJob} />

      <TransportBar project={project} analysis={analysis} />

      <div className="flex-1 flex overflow-hidden">
        {/* ─ Main Editor ─ */}
        <div className="flex-1 flex flex-col min-w-0 bg-[#060608]">
          {/* Timeline: chord + section labels */}
          <div className="h-20 bg-card border-b border-white/5 flex flex-col justify-end px-4 relative overflow-hidden" dir="ltr">
            {analysis?.structure?.sections?.map((sec: any, i: number) => (
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
              {analysis?.chords?.chords?.slice(0, 30).map((chord: any, i: number) => (
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

          {/* Tracks */}
          <div className="flex-1 overflow-y-auto overflow-x-hidden relative">
            {!project.audioFileName && !arrangement ? (
              <div className="absolute inset-0 flex flex-col items-center justify-center text-center p-8">
                <div className="w-24 h-24 rounded-full bg-white/5 flex items-center justify-center mb-6 border border-white/10 border-dashed">
                  <Upload className="w-10 h-10 text-muted-foreground" />
                </div>
                <h3 className="text-xl font-display font-semibold mb-2">{t("Drop Audio File to Analyze")}</h3>
                <p className="text-muted-foreground max-w-md mb-6">{t("Upload a track to extract chords, BPM, stems, and structure. Or go straight to arrangement generation.")}</p>
                <input type="file" ref={fileInputRef} className="hidden" accept="audio/*" onChange={handleUpload} />
                <Button variant="glow" onClick={() => fileInputRef.current?.click()}>
                  <Upload className="w-4 h-4 mr-2" /> {t("Upload Audio")}
                </Button>
              </div>
            ) : (
              <div className="w-full">
                {project.audioFileName && (
                  <div className="flex border-b border-white/10 h-32 group">
                    <div className="w-64 bg-card border-r border-white/10 flex items-center px-4">
                      <span className="font-medium text-sm text-white">{t("Original Audio")}</span>
                    </div>
                    <div className="flex-1 bg-[#0a0a0c] relative">
                      {analysis?.waveformData ? (
                        <WaveformVisualizer data={analysis.waveformData} />
                      ) : (
                        <div className="absolute inset-0 flex items-center justify-center">
                          {activeJobId
                            ? <Loader2 className="w-6 h-6 animate-spin text-primary" />
                            : <Button size="sm" variant="outline" onClick={handleAnalyze}>{t("Analyze Audio")}</Button>
                          }
                        </div>
                      )}
                    </div>
                  </div>
                )}
                {arrangement?.tracks?.map((track: any) => (
                  <TrackLane key={track.id} track={track} />
                ))}
              </div>
            )}
          </div>
        </div>

        {/* ─ Right Panel ─ */}
        <div className="w-[340px] border-l border-white/10 bg-card flex flex-col z-20 shadow-2xl relative">
          <Tabs defaultValue="analysis" className="flex-1 flex flex-col">
            <div className="p-4 border-b border-white/5">
              <TabsList className="w-full grid grid-cols-3">
                <TabsTrigger value="analysis">{t("Analyze")}</TabsTrigger>
                <TabsTrigger value="arrange">{t("Arrange")}</TabsTrigger>
                <TabsTrigger value="export">{t("Export")}</TabsTrigger>
              </TabsList>
            </div>

            <div className="flex-1 overflow-y-auto p-4 custom-scrollbar">

              {/* ── ANALYSIS TAB ── */}
              <TabsContent value="analysis" className="space-y-6 mt-0">
                {!analysis ? (
                  <div className="text-center py-10 space-y-4">
                    <Activity className="w-12 h-12 text-muted-foreground mx-auto opacity-20" />
                    <p className="text-sm text-muted-foreground">{t("No analysis data yet.")}</p>
                    <Button onClick={handleAnalyze} disabled={!project.audioFileName || !!activeJobId} className="w-full">
                      <Zap className="w-4 h-4 mr-2" /> {t("Start Analysis")}
                    </Button>
                    {!project.audioFileName && (
                      <>
                        <input type="file" ref={fileInputRef} className="hidden" accept="audio/*" onChange={handleUpload} />
                        <Button variant="outline" className="w-full" onClick={() => fileInputRef.current?.click()}>
                          <Upload className="w-4 h-4 mr-2" /> {t("Upload Audio")}
                        </Button>
                      </>
                    )}
                  </div>
                ) : (
                  <>
                    {/* Mock indicator on analysis card */}
                    {(analysis.rhythm as any)?.isMock && (
                      <div className="flex items-center gap-2 text-amber-400 text-xs bg-amber-500/10 border border-amber-500/20 rounded px-3 py-2">
                        <AlertTriangle className="w-3 h-3 flex-shrink-0" />
                        {t("These are simulated results (MOCK MODE)")}
                      </div>
                    )}

                    <div className="daw-panel p-4">
                      <div className="flex items-center justify-between mb-3">
                        <h4 className="text-xs font-display font-bold text-muted-foreground uppercase tracking-widest">{t("Key & Tempo")}</h4>
                        <button
                          onClick={() => setShowCorrections(true)}
                          className="flex items-center gap-1 text-xs text-muted-foreground hover:text-accent transition-colors"
                        >
                          <Edit3 className="w-3 h-3" /> {t("Edit")}
                        </button>
                      </div>
                      <div className="grid grid-cols-2 gap-4" dir="ltr">
                        <div className="bg-black/30 rounded p-3 text-center border border-white/5">
                          <div className="text-2xl font-bold text-accent text-glow-accent">{analysis.key.globalKey} {analysis.key.mode}</div>
                          <div className="text-[10px] uppercase text-muted-foreground mt-1">{t("Key")}</div>
                        </div>
                        <div className="bg-black/30 rounded p-3 text-center border border-white/5">
                          <div className="text-2xl font-bold text-primary text-glow-primary">{Math.round(analysis.rhythm.bpm)}</div>
                          <div className="text-[10px] uppercase text-muted-foreground mt-1">{t("BPM")}</div>
                        </div>
                      </div>
                    </div>

                    <div className="daw-panel p-4">
                      <h4 className="text-xs font-display font-bold text-muted-foreground uppercase tracking-widest mb-3">{t("Structure")}</h4>
                      <div className="space-y-2">
                        {analysis.structure.sections.map((sec: any, i: number) => (
                          <div key={i} className="flex justify-between items-center text-sm p-2 rounded bg-white/5">
                            <span className="capitalize text-white/80">{t(sec.label)}</span>
                            <span className="text-muted-foreground font-mono text-xs" dir="ltr">{formatTime(sec.startTime)}</span>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div className="daw-panel p-4">
                      <h4 className="text-xs font-display font-bold text-muted-foreground uppercase tracking-widest mb-3">{t("Chord Progression")}</h4>
                      <p className="text-sm font-mono text-white/80 leading-relaxed" dir="ltr">
                        {analysis.chords?.leadSheet || analysis.chords?.chords?.slice(0, 8).map((c: any) => c.chord).join(" | ")}
                      </p>
                    </div>

                    <Button variant="outline" className="w-full" onClick={handleAnalyze} disabled={!!activeJobId}>
                      <Zap className="w-4 h-4 mr-2" /> {t("Re-analyze")}
                    </Button>
                  </>
                )}
              </TabsContent>

              {/* ── ARRANGE TAB ── */}
              <TabsContent value="arrange" className="space-y-4 mt-0">
                <div className="daw-panel p-4">
                  <h4 className="text-xs font-display font-bold text-muted-foreground uppercase tracking-widest mb-4">{t("Style")}</h4>
                  <div className="grid grid-cols-2 gap-2 max-h-72 overflow-y-auto custom-scrollbar pr-1">
                    {styles?.map((style: any) => (
                      <button
                        key={style.id}
                        onClick={() => setSelectedStyle(style.id)}
                        className={cn(
                          "p-3 text-left rounded border transition-all ltr:text-left rtl:text-right",
                          selectedStyle === style.id
                            ? "border-primary/70 bg-primary/20 shadow-[0_0_12px_rgba(0,240,255,0.2)]"
                            : "border-white/10 bg-white/5 hover:bg-primary/10 hover:border-primary/30"
                        )}
                      >
                        <div className={cn("text-sm font-bold", selectedStyle === style.id ? "text-primary" : "text-white")}>{t(style.name)}</div>
                        <div className="text-[10px] text-muted-foreground">{t(style.genre)}</div>
                      </button>
                    ))}
                  </div>
                </div>

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

                <Button variant="glow" className="w-full" onClick={handleArrange} disabled={!!activeJobId}>
                  <Layers className="w-4 h-4 mr-2" /> {t("Generate Arrangement")}
                </Button>

                {arrangement && (
                  <p className="text-xs text-center text-green-400/80 flex items-center justify-center gap-1">
                    <CheckCircle2 className="w-3 h-3" /> {t("Arrangement ready")} — {styles?.find((s: any) => s.id === arrangement.styleId)?.name}
                  </p>
                )}
              </TabsContent>

              {/* ── EXPORT TAB ── */}
              <TabsContent value="export" className="space-y-4 mt-0">
                <div className="daw-panel p-4">
                  <h4 className="text-xs font-display font-bold text-muted-foreground uppercase tracking-widest mb-3">Score &amp; MIDI</h4>
                  <div className="space-y-2">
                    {([["midi", "MIDI Tracks"], ["musicxml", "MusicXML Score"], ["pdf", "Lead Sheet PDF"]] as [string, string][]).map(([key, label]) => (
                      <label key={key} className="flex items-center gap-3 p-3 rounded border border-white/5 bg-black/20 cursor-pointer hover:bg-white/5">
                        <input
                          type="checkbox"
                          className="accent-primary w-4 h-4"
                          checked={!!selectedFormats[key]}
                          onChange={e => setSelectedFormats(f => ({ ...f, [key]: e.target.checked }))}
                        />
                        <span className="text-sm" dir="ltr">{t(label)}</span>
                      </label>
                    ))}
                  </div>
                  <Button className="w-full mt-3" variant="secondary" onClick={handleExport} disabled={!!activeJobId || !arrangement}>
                    <Download className="w-4 h-4 mr-2" /> {t("Export Files")}
                  </Button>
                  {!arrangement && <p className="text-xs text-muted-foreground mt-2 text-center">{t("Generate an arrangement first")}</p>}
                </div>

                <div className="daw-panel p-4">
                  <h4 className="text-xs font-display font-bold text-muted-foreground uppercase tracking-widest mb-3">Audio Render</h4>
                  <div className="space-y-2">
                    {([["wav", "WAV Audio (Lossless)"], ["flac", "FLAC Audio (Lossless)"], ["mp3", "MP3 320kbps"], ["stems", "Separated Stems"]] as [string, string][]).map(([key, label]) => (
                      <label key={key} className="flex items-center gap-3 p-3 rounded border border-white/5 bg-black/20 cursor-pointer hover:bg-white/5">
                        <input
                          type="checkbox"
                          className="accent-primary w-4 h-4"
                          checked={!!selectedFormats[key]}
                          onChange={e => setSelectedFormats(f => ({ ...f, [key]: e.target.checked }))}
                        />
                        <span className="text-sm" dir="ltr">{t(label)}</span>
                      </label>
                    ))}
                  </div>
                  <Button className="w-full mt-3 bg-accent hover:bg-accent/80 text-white" onClick={handleRender} disabled={!!activeJobId || !arrangement}>
                    <Music className="w-4 h-4 mr-2" /> {t("Render Audio")}
                  </Button>
                  {!arrangement && <p className="text-xs text-muted-foreground mt-2 text-center">{t("Generate an arrangement first")}</p>}
                </div>

                {projectFiles.length > 0 && (
                  <div className="daw-panel p-4">
                    <h4 className="text-xs font-display font-bold text-muted-foreground uppercase tracking-widest mb-3">{t("Generated Files")}</h4>
                    <div className="space-y-2">
                      {(projectFiles as any[]).map((f: any) => {
                        const iconMap: Record<string, any> = {
                          mid: FileMusic, midi: FileMusic,
                          musicxml: FileText, txt: FileText, pdf: FileText,
                          wav: FileAudio, flac: FileAudio, mp3: FileAudio,
                        };
                        const Icon = iconMap[f.fileType] || HardDrive;
                        const sizeKb = f.fileSizeBytes ? Math.round(f.fileSizeBytes / 1024) : null;
                        return (
                          <a
                            key={f.id}
                            href={`/api/projects/${projectId}/files/${encodeURIComponent(f.fileName)}/download`}
                            download={f.fileName}
                            className="flex items-center justify-between p-3 rounded border border-white/5 bg-black/20 hover:bg-white/5 group cursor-pointer"
                          >
                            <div className="flex items-center gap-3 min-w-0">
                              <Icon className="w-4 h-4 text-primary flex-shrink-0" />
                              <div className="min-w-0">
                                <p className="text-sm font-mono truncate" dir="ltr">{f.fileName}</p>
                                <p className="text-xs text-muted-foreground" dir="ltr">
                                  {f.fileType.toUpperCase()}{sizeKb ? ` · ${sizeKb > 1024 ? (sizeKb / 1024).toFixed(1) + "MB" : sizeKb + "KB"}` : ""}
                                </p>
                              </div>
                            </div>
                            <Download className="w-4 h-4 text-muted-foreground group-hover:text-primary flex-shrink-0" />
                          </a>
                        );
                      })}
                    </div>
                  </div>
                )}
              </TabsContent>
            </div>
          </Tabs>
        </div>
      </div>

      {/* Manual Corrections modal */}
      {showCorrections && (
        <CorrectionsDrawer
          analysis={analysis}
          projectId={projectId}
          onClose={() => setShowCorrections(false)}
          onSaved={() => {
            invalidateAll();
            setShowCorrections(false);
          }}
        />
      )}
    </div>
  );
}
