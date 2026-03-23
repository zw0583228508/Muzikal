import { useEffect, useRef, useState, useCallback } from "react";
import WaveSurfer from "wavesurfer.js";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { Play, Pause, ZoomIn, ZoomOut, SkipBack, Volume2 } from "lucide-react";
import { cn, formatTime } from "@/lib/utils";

interface WaveformPlayerProps {
  audioUrl?: string;
  peaks?: number[];
  duration?: number;
  className?: string;
  onTimeUpdate?: (time: number) => void;
}

const WAVE_COLOR = "#4c1d95";
const PROGRESS_COLOR = "#7c3aed";
const CURSOR_COLOR = "#a78bfa";

export function WaveformPlayer({
  audioUrl,
  peaks,
  duration,
  className,
  onTimeUpdate,
}: WaveformPlayerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const minimapRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WaveSurfer | null>(null);

  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [totalDuration, setTotalDuration] = useState(duration ?? 0);
  const [zoom, setZoom] = useState(50);
  const [volume, setVolume] = useState(80);
  const [ready, setReady] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const initWaveSurfer = useCallback(() => {
    if (!containerRef.current) return;

    if (wsRef.current) {
      wsRef.current.destroy();
      wsRef.current = null;
    }

    setReady(false);
    setError(null);
    setLoading(!!audioUrl);

    const ws = WaveSurfer.create({
      container: containerRef.current,
      waveColor: WAVE_COLOR,
      progressColor: PROGRESS_COLOR,
      cursorColor: CURSOR_COLOR,
      cursorWidth: 2,
      height: 96,
      barWidth: 2,
      barGap: 1,
      barRadius: 2,
      normalize: true,
      interact: true,
      fillParent: true,
    });

    ws.on("ready", () => {
      setReady(true);
      setLoading(false);
      setTotalDuration(ws.getDuration());
    });

    ws.on("play", () => setIsPlaying(true));
    ws.on("pause", () => setIsPlaying(false));
    ws.on("finish", () => setIsPlaying(false));

    ws.on("timeupdate", (t: number) => {
      setCurrentTime(t);
      onTimeUpdate?.(t);
    });

    ws.on("error", (e: Error) => {
      setLoading(false);
      setError(e.message ?? "שגיאה בטעינת האודיו");
    });

    wsRef.current = ws;

    if (audioUrl) {
      const channelData = peaks?.length ? [new Float32Array(peaks)] : undefined;
      ws.load(audioUrl, channelData, duration);
    } else if (peaks?.length) {
      const dur = duration ?? peaks.length / 22050;
      ws.load("", [new Float32Array(peaks)], dur);
      setTotalDuration(dur);
      setReady(true);
    }
  }, [audioUrl, peaks, duration, onTimeUpdate]);

  useEffect(() => {
    initWaveSurfer();
    return () => {
      wsRef.current?.destroy();
      wsRef.current = null;
    };
  }, [initWaveSurfer]);

  useEffect(() => {
    if (wsRef.current && ready) {
      wsRef.current.setVolume(volume / 100);
    }
  }, [volume, ready]);

  useEffect(() => {
    if (wsRef.current && ready) {
      wsRef.current.zoom(zoom);
    }
  }, [zoom, ready]);

  const handlePlayPause = () => {
    if (!wsRef.current || !ready) return;
    wsRef.current.playPause();
  };

  const handleSkipBack = () => {
    if (!wsRef.current || !ready) return;
    wsRef.current.setTime(0);
    setCurrentTime(0);
  };

  const handleZoomIn = () => setZoom((z) => Math.min(z + 20, 200));
  const handleZoomOut = () => setZoom((z) => Math.max(z - 20, 10));

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.code === "Space") { e.preventDefault(); handlePlayPause(); }
      if (e.code === "ArrowLeft") wsRef.current?.setTime(Math.max(0, currentTime - 5));
      if (e.code === "ArrowRight") wsRef.current?.setTime(Math.min(totalDuration, currentTime + 5));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [ready, currentTime, totalDuration]);

  return (
    <div className={cn("flex flex-col gap-2 select-none", className)} dir="ltr">
      {/* Waveform canvas */}
      <div className="relative rounded-lg overflow-hidden bg-[#080810] border border-white/10">
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center z-10 bg-black/40 backdrop-blur-sm">
            <div className="flex flex-col items-center gap-2">
              <div className="w-6 h-6 border-2 border-primary/60 border-t-primary rounded-full animate-spin" />
              <span className="text-xs text-muted-foreground">טוען גל קול...</span>
            </div>
          </div>
        )}
        {error && (
          <div className="absolute inset-0 flex items-center justify-center z-10">
            <span className="text-xs text-destructive">{error}</span>
          </div>
        )}
        <div ref={containerRef} className="w-full" style={{ minHeight: 96 }} />
      </div>

      {/* Controls */}
      <div className="flex items-center gap-3 px-1">
        <div className="flex items-center gap-1">
          <Button size="icon" variant="ghost" className="h-7 w-7" onClick={handleSkipBack} disabled={!ready}>
            <SkipBack className="w-3.5 h-3.5" />
          </Button>
          <Button
            size="icon"
            variant="ghost"
            className={cn("h-8 w-8 rounded-full transition-all", ready ? "bg-primary/20 hover:bg-primary/30 text-primary" : "opacity-40")}
            onClick={handlePlayPause}
            disabled={!ready || !audioUrl}
          >
            {isPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4 ml-0.5" />}
          </Button>
        </div>

        <span className="text-[11px] font-mono text-muted-foreground tabular-nums min-w-[90px]">
          {formatTime(currentTime)} / {formatTime(totalDuration)}
        </span>

        <div className="flex items-center gap-1 ml-auto">
          <Button size="icon" variant="ghost" className="h-6 w-6" onClick={handleZoomOut} disabled={zoom <= 10}>
            <ZoomOut className="w-3 h-3" />
          </Button>
          <span className="text-[10px] text-muted-foreground w-8 text-center">{zoom}x</span>
          <Button size="icon" variant="ghost" className="h-6 w-6" onClick={handleZoomIn} disabled={zoom >= 200}>
            <ZoomIn className="w-3 h-3" />
          </Button>
        </div>

        {audioUrl && (
          <div className="flex items-center gap-1.5 w-24">
            <Volume2 className="w-3 h-3 text-muted-foreground shrink-0" />
            <Slider
              value={[volume]}
              onValueChange={([v]) => setVolume(v)}
              min={0}
              max={100}
              className="h-1"
            />
          </div>
        )}
      </div>

      {!audioUrl && peaks?.length && (
        <p className="text-[10px] text-muted-foreground/60 text-center">
          מצב ויזואלי בלבד — העלה אודיו לניגון
        </p>
      )}
    </div>
  );
}
