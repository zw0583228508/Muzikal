import { useState, useRef } from "react";
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
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { JobProgress } from "@/components/job-progress";
import { 
  Play, Pause, Square, SkipBack, Search, Volume2, Settings2, 
  ChevronLeft, Upload, Zap, Download, Layers, Activity, Music, 
  Settings, Loader2
} from "lucide-react";
import { formatTime, cn } from "@/lib/utils";

// --- Sub-components for DAW ---

function TransportBar({ project, analysis }: { project: any, analysis: any }) {
  const [isPlaying, setIsPlaying] = useState(false);
  const [time, setTime] = useState(0);

  // Fake playhead for visuals
  useState(() => {
    let interval: any;
    if (isPlaying) {
      interval = setInterval(() => setTime(t => t + 0.1), 100);
    }
    return () => clearInterval(interval);
  });

  return (
    <div className="h-16 border-b border-white/10 bg-background/95 backdrop-blur flex items-center px-4 justify-between sticky top-0 z-40">
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="icon" asChild className="mr-2">
          <Link href="/"><ChevronLeft className="w-5 h-5" /></Link>
        </Button>
        <div className="flex gap-1 bg-black/40 p-1 rounded-lg border border-white/5">
          <Button variant="ghost" size="icon" className="h-8 w-8 hover:bg-white/10" onClick={() => setTime(0)}>
            <SkipBack className="w-4 h-4" />
          </Button>
          <Button variant="ghost" size="icon" className="h-8 w-8 hover:bg-white/10" onClick={() => setIsPlaying(false)}>
            <Square className="w-4 h-4" />
          </Button>
          <Button variant={isPlaying ? "glow" : "ghost"} size="icon" className="h-8 w-8" onClick={() => setIsPlaying(!isPlaying)}>
            {isPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4 ml-0.5" />}
          </Button>
        </div>
        
        <div className="font-mono text-xl font-light text-primary text-glow mx-4 tracking-wider bg-black/40 px-4 py-1 rounded border border-primary/20 shadow-inner">
          {formatTime(time)}
        </div>
      </div>

      <div className="flex items-center gap-6 text-sm font-display uppercase tracking-widest text-muted-foreground">
        <div className="flex flex-col items-center">
          <span className="text-white font-bold">{analysis?.rhythm?.bpm ? Math.round(analysis.rhythm.bpm) : '120'}</span>
          <span className="text-[10px]">BPM</span>
        </div>
        <div className="flex flex-col items-center">
          <span className="text-primary font-bold">{analysis?.rhythm?.timeSignatureNumerator || '4'}/{analysis?.rhythm?.timeSignatureDenominator || '4'}</span>
          <span className="text-[10px]">TIME</span>
        </div>
        <div className="flex flex-col items-center">
          <span className="text-accent font-bold">{analysis?.key?.globalKey || 'C'} {analysis?.key?.mode || 'Maj'}</span>
          <span className="text-[10px]">KEY</span>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <h2 className="font-display font-semibold text-lg text-white/80 mr-4 truncate max-w-[200px]">{project?.name}</h2>
        <Button variant="outline" size="sm" className="hidden lg:flex"><Settings2 className="w-4 h-4 mr-2" /> Settings</Button>
      </div>
    </div>
  );
}

function TrackLane({ track }: { track: any }) {
  return (
    <div className="flex border-b border-white/5 h-24 group relative">
      {/* Track Header */}
      <div className="w-64 bg-card border-r border-white/10 flex flex-col justify-center px-3 z-10">
        <div className="flex justify-between items-center mb-2">
          <span className="font-medium text-sm text-white truncate flex items-center gap-2">
            <div className="w-2 h-2 rounded-full" style={{ backgroundColor: track.color || '#00f0ff' }} />
            {track.name}
          </span>
          <div className="flex gap-1">
            <button className={cn("w-6 h-6 rounded text-xs font-bold transition-colors", track.muted ? "bg-accent/20 text-accent" : "bg-white/5 hover:bg-white/10")}>M</button>
            <button className={cn("w-6 h-6 rounded text-xs font-bold transition-colors", track.soloed ? "bg-yellow-500/20 text-yellow-500" : "bg-white/5 hover:bg-white/10")}>S</button>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Volume2 className="w-3 h-3 text-muted-foreground" />
          <Slider defaultValue={[track.volume * 100]} max={100} className="w-full" />
        </div>
      </div>
      {/* Track Content (Piano Roll Placeholder) */}
      <div className="flex-1 bg-[#0a0a0c] relative overflow-hidden flex items-center px-4">
        <div className="absolute inset-0 bg-[linear-gradient(90deg,rgba(255,255,255,0.02)_1px,transparent_1px)] bg-[size:2rem_100%]" />
        {track.notes?.slice(0, 50).map((note: any, i: number) => (
          <div 
            key={i}
            className="absolute h-2 rounded-sm shadow-sm"
            style={{
              left: `${note.startTime * 20}px`,
              width: `${note.duration * 20}px`,
              bottom: `${(note.pitch % 24) * 4}px`,
              backgroundColor: track.color || '#00f0ff',
              opacity: note.velocity / 127
            }}
          />
        ))}
      </div>
    </div>
  );
}

function WaveformVisualizer({ data }: { data?: number[] }) {
  if (!data || data.length === 0) return <div className="h-32 flex items-center justify-center text-muted-foreground">No waveform data</div>;
  
  // Downsample for rendering performance
  const displayData = data.filter((_, i) => i % Math.ceil(data.length / 500) === 0).slice(0, 500);
  
  return (
    <div className="h-32 w-full flex items-end gap-[1px] px-4 opacity-70">
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

// --- Main Page Component ---

export default function ProjectStudio() {
  const params = useParams();
  const projectId = parseInt(params.id || "0", 10);
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [activeJobId, setActiveJobId] = useState<string | null>(null);

  // Data Hooks
  const { data: project, isLoading: isProjLoading } = useGetProject(projectId);
  const { data: analysis } = useGetAnalysisResults(projectId, { query: { retry: false } });
  const { data: arrangement } = useGetArrangement(projectId, { query: { retry: false } });
  const { data: styles } = useListStyles();

  // Mutations
  const uploadMut = useUploadAudio();
  const analyzeMut = useStartAnalysis();
  const arrangeMut = useGenerateArrangement();
  const exportMut = useExportProject();

  // Job Polling
  const { job: activeJob } = useJobPolling(activeJobId, () => {
    // On complete, invalidate relevant queries
    queryClient.invalidateQueries({ queryKey: [`/api/projects/${projectId}`] });
    queryClient.invalidateQueries({ queryKey: [`/api/projects/${projectId}/analysis`] });
    queryClient.invalidateQueries({ queryKey: [`/api/projects/${projectId}/arrangement`] });
    setActiveJobId(null);
  });

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const res = await uploadMut.mutateAsync({ projectId, data: { file } });
      setActiveJobId(res.jobId);
    } catch (err) {
      console.error(err);
      alert("Upload failed");
    }
  };

  const handleAnalyze = async () => {
    try {
      const res = await analyzeMut.mutateAsync({ projectId });
      setActiveJobId(res.jobId);
    } catch (err) {
      console.error(err);
      alert("Analysis failed to start");
    }
  };

  const handleArrange = async () => {
    try {
      const styleId = styles?.[0]?.id || "pop"; // Default fallback
      const res = await arrangeMut.mutateAsync({ 
        projectId, 
        data: { styleId, density: 0.8, humanize: true } 
      });
      setActiveJobId(res.jobId);
    } catch (err) {
      console.error(err);
    }
  };

  if (isProjLoading) return <div className="h-screen flex items-center justify-center bg-background"><Loader2 className="w-8 h-8 animate-spin text-primary" /></div>;
  if (!project) return <div className="p-8 text-center text-white">Project not found</div>;

  return (
    <div className="h-screen flex flex-col bg-background overflow-hidden selection:bg-primary/30 text-foreground">
      <JobProgress job={activeJob} />
      
      <TransportBar project={project} analysis={analysis} />

      <div className="flex-1 flex overflow-hidden">
        {/* Main Editor Area */}
        <div className="flex-1 flex flex-col min-w-0 bg-[#060608]">
          
          {/* Timeline Header (Chords & Sections) */}
          <div className="h-20 bg-card border-b border-white/5 flex flex-col justify-end px-4 relative overflow-hidden">
            {analysis?.structure?.sections?.map((sec: any, i: number) => (
              <div 
                key={i} 
                className="absolute top-0 h-6 border-l border-white/20 px-2 text-[10px] font-bold tracking-widest text-white/50 uppercase"
                style={{ left: `${sec.startTime * 20}px`, width: `${(sec.endTime - sec.startTime) * 20}px` }}
              >
                <div className="absolute inset-0 bg-accent/10 opacity-50" />
                {sec.label}
              </div>
            ))}
            
            <div className="flex h-8 items-end gap-1 relative z-10 bottom-2">
              {analysis?.chords?.chords?.slice(0, 30).map((chord: any, i: number) => (
                <div 
                  key={i}
                  className="bg-primary/20 text-primary border border-primary/30 px-2 py-0.5 rounded text-xs font-medium shadow-[0_0_10px_rgba(0,240,255,0.1)] whitespace-nowrap"
                  style={{ position: 'absolute', left: `${chord.startTime * 20}px` }}
                >
                  {chord.chord}
                </div>
              ))}
            </div>
          </div>

          {/* Center Timeline / Tracks Area */}
          <div className="flex-1 overflow-y-auto overflow-x-hidden relative">
            {!project.audioFileName && !arrangement ? (
              <div className="absolute inset-0 flex flex-col items-center justify-center text-center p-8">
                <div className="w-24 h-24 rounded-full bg-white/5 flex items-center justify-center mb-6 border border-white/10 border-dashed">
                  <Upload className="w-10 h-10 text-muted-foreground" />
                </div>
                <h3 className="text-xl font-display font-semibold mb-2">Drop Audio File to Analyze</h3>
                <p className="text-muted-foreground max-w-md mb-6">Upload a track to extract chords, BPM, stems, and structure. Or go straight to arrangement generation.</p>
                <input type="file" ref={fileInputRef} className="hidden" accept="audio/*" onChange={handleUpload} />
                <div className="flex gap-4">
                  <Button variant="glow" onClick={() => fileInputRef.current?.click()}>
                    <Upload className="w-4 h-4 mr-2" /> Upload Audio
                  </Button>
                </div>
              </div>
            ) : (
              <div className="w-full">
                {/* Waveform track */}
                {project.audioFileName && (
                  <div className="flex border-b border-white/10 h-32 group">
                    <div className="w-64 bg-card border-r border-white/10 flex items-center px-4">
                      <span className="font-medium text-sm text-white">Original Audio</span>
                    </div>
                    <div className="flex-1 bg-[#0a0a0c] relative">
                      {analysis?.waveformData ? (
                        <WaveformVisualizer data={analysis.waveformData} />
                      ) : (
                        <div className="absolute inset-0 flex items-center justify-center">
                          {activeJobId ? <Loader2 className="w-6 h-6 animate-spin text-primary" /> : <Button size="sm" variant="outline" onClick={handleAnalyze}>Analyze Audio</Button>}
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Arrangement Tracks */}
                {arrangement?.tracks?.map((track) => (
                  <TrackLane key={track.id} track={track} />
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right Panel - Inspector */}
        <div className="w-[340px] border-l border-white/10 bg-card flex flex-col z-20 shadow-2xl relative">
          <Tabs defaultValue="analysis" className="flex-1 flex flex-col">
            <div className="p-4 border-b border-white/5">
              <TabsList className="w-full grid grid-cols-3">
                <TabsTrigger value="analysis">Analyze</TabsTrigger>
                <TabsTrigger value="arrange">Arrange</TabsTrigger>
                <TabsTrigger value="export">Export</TabsTrigger>
              </TabsList>
            </div>

            <div className="flex-1 overflow-y-auto p-4 custom-scrollbar">
              
              {/* ANALYSIS TAB */}
              <TabsContent value="analysis" className="space-y-6 mt-0">
                {!analysis ? (
                  <div className="text-center py-10 space-y-4">
                    <Activity className="w-12 h-12 text-muted-foreground mx-auto opacity-20" />
                    <p className="text-sm text-muted-foreground">No analysis data yet.</p>
                    <Button onClick={handleAnalyze} disabled={!project.audioFileName || !!activeJobId} className="w-full">
                      <Zap className="w-4 h-4 mr-2" /> Start Analysis
                    </Button>
                  </div>
                ) : (
                  <>
                    <div className="daw-panel p-4">
                      <h4 className="text-xs font-display font-bold text-muted-foreground uppercase tracking-widest mb-3">Key & Tempo</h4>
                      <div className="grid grid-cols-2 gap-4">
                        <div className="bg-black/30 rounded p-3 text-center border border-white/5">
                          <div className="text-2xl font-bold text-accent text-glow-accent">{analysis.key.globalKey} {analysis.key.mode}</div>
                          <div className="text-[10px] uppercase text-muted-foreground mt-1">Key</div>
                        </div>
                        <div className="bg-black/30 rounded p-3 text-center border border-white/5">
                          <div className="text-2xl font-bold text-primary text-glow-primary">{Math.round(analysis.rhythm.bpm)}</div>
                          <div className="text-[10px] uppercase text-muted-foreground mt-1">BPM</div>
                        </div>
                      </div>
                    </div>

                    <div className="daw-panel p-4">
                      <h4 className="text-xs font-display font-bold text-muted-foreground uppercase tracking-widest mb-3">Structure</h4>
                      <div className="space-y-2">
                        {analysis.structure.sections.map((sec, i) => (
                          <div key={i} className="flex justify-between items-center text-sm p-2 rounded bg-white/5">
                            <span className="capitalize text-white/80">{sec.label}</span>
                            <span className="text-muted-foreground font-mono text-xs">{formatTime(sec.startTime)}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </>
                )}
              </TabsContent>

              {/* ARRANGE TAB */}
              <TabsContent value="arrange" className="space-y-6 mt-0">
                <div className="daw-panel p-4">
                  <h4 className="text-xs font-display font-bold text-muted-foreground uppercase tracking-widest mb-4">Style</h4>
                  <div className="grid grid-cols-2 gap-2">
                    {styles?.slice(0,4).map(style => (
                      <button key={style.id} className="p-3 text-left rounded border border-white/10 bg-white/5 hover:bg-primary/20 hover:border-primary/50 transition-all group">
                        <div className="text-sm font-bold text-white group-hover:text-primary">{style.name}</div>
                        <div className="text-xs text-muted-foreground">{style.genre}</div>
                      </button>
                    ))}
                  </div>
                </div>

                <div className="daw-panel p-4 space-y-4">
                  <div>
                    <div className="flex justify-between mb-2">
                      <h4 className="text-xs font-display font-bold text-muted-foreground uppercase tracking-widest">Density</h4>
                      <span className="text-xs text-primary">80%</span>
                    </div>
                    <Slider defaultValue={[80]} max={100} />
                  </div>
                  <div>
                    <div className="flex justify-between mb-2">
                      <h4 className="text-xs font-display font-bold text-muted-foreground uppercase tracking-widest">Tempo Factor</h4>
                      <span className="text-xs text-white">1.0x</span>
                    </div>
                    <Slider defaultValue={[50]} max={100} />
                  </div>
                </div>

                <Button variant="glow" className="w-full" onClick={handleArrange} disabled={!!activeJobId}>
                  <Layers className="w-4 h-4 mr-2" /> Generate Arrangement
                </Button>
              </TabsContent>

              {/* EXPORT TAB */}
              <TabsContent value="export" className="space-y-6 mt-0">
                <div className="daw-panel p-4">
                  <h4 className="text-xs font-display font-bold text-muted-foreground uppercase tracking-widest mb-4">Formats</h4>
                  <div className="space-y-2">
                    {['MIDI Tracks', 'MusicXML Score', 'WAV Audio', 'Separated Stems'].map(fmt => (
                      <label key={fmt} className="flex items-center gap-3 p-3 rounded border border-white/5 bg-black/20 cursor-pointer hover:bg-white/5">
                        <input type="checkbox" className="accent-primary w-4 h-4 rounded bg-transparent border-white/20" defaultChecked />
                        <span className="text-sm">{fmt}</span>
                      </label>
                    ))}
                  </div>
                </div>
                
                <Button className="w-full" onClick={() => exportMut.mutate({ projectId, data: { formats: ['midi', 'wav'] } })} disabled={!!activeJobId}>
                  <Download className="w-4 h-4 mr-2" /> Export Files
                </Button>
              </TabsContent>
            </div>
          </Tabs>
        </div>
      </div>
    </div>
  );
}
