import { useRef, useState, useEffect, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { Play, Pause, SkipBack, Volume2, VolumeX } from "lucide-react";
import { formatTime } from "@/lib/utils";
import { useTranslation } from "react-i18next";

interface AudioPlayerProps {
  projectId: number;
  hasAudio: boolean;
  className?: string;
  onTimeUpdate?: (currentTime: number, duration: number) => void;
}

export function AudioPlayer({ projectId, hasAudio, className, onTimeUpdate }: AudioPlayerProps) {
  const { t } = useTranslation();
  const audioRef = useRef<HTMLAudioElement>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [volume, setVolume] = useState(1);
  const [muted, setMuted] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  const audioUrl = `/api/projects/${projectId}/audio`;

  const togglePlay = useCallback(() => {
    const audio = audioRef.current;
    if (!audio || !hasAudio || error) return;
    if (isPlaying) {
      audio.pause();
    } else {
      audio.play().catch(() => setError(true));
    }
  }, [isPlaying, hasAudio, error]);

  const handleSeek = useCallback((value: number[]) => {
    const audio = audioRef.current;
    if (!audio || !duration) return;
    audio.currentTime = (value[0] / 100) * duration;
  }, [duration]);

  const handleVolumeChange = useCallback((value: number[]) => {
    const audio = audioRef.current;
    if (!audio) return;
    const v = value[0] / 100;
    setVolume(v);
    audio.volume = v;
    setMuted(v === 0);
  }, []);

  const handleMuteToggle = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.muted = !muted;
    setMuted(!muted);
  }, [muted]);

  const handleSkipBack = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.currentTime = 0;
    setCurrentTime(0);
  }, []);

  // Keyboard shortcut: space bar
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.code === "Space" && e.target === document.body) {
        e.preventDefault();
        togglePlay();
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [togglePlay]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;

    const onPlay = () => setIsPlaying(true);
    const onPause = () => setIsPlaying(false);
    const onEnded = () => { setIsPlaying(false); setCurrentTime(0); audio.currentTime = 0; };
    const handleTimeUpdate = () => {
      setCurrentTime(audio.currentTime);
      onTimeUpdate?.(audio.currentTime, audio.duration || 0);
    };
    const onDurationChange = () => setDuration(audio.duration || 0);
    const onWaiting = () => setLoading(true);
    const onCanPlay = () => { setLoading(false); setError(false); };
    const onError = () => { setLoading(false); setError(true); };

    audio.addEventListener("play", onPlay);
    audio.addEventListener("pause", onPause);
    audio.addEventListener("ended", onEnded);
    audio.addEventListener("timeupdate", handleTimeUpdate);
    audio.addEventListener("durationchange", onDurationChange);
    audio.addEventListener("waiting", onWaiting);
    audio.addEventListener("canplay", onCanPlay);
    audio.addEventListener("error", onError);

    return () => {
      audio.removeEventListener("play", onPlay);
      audio.removeEventListener("pause", onPause);
      audio.removeEventListener("ended", onEnded);
      audio.removeEventListener("timeupdate", handleTimeUpdate);
      audio.removeEventListener("durationchange", onDurationChange);
      audio.removeEventListener("waiting", onWaiting);
      audio.removeEventListener("canplay", onCanPlay);
      audio.removeEventListener("error", onError);
    };
  }, []);

  const seekPct = duration > 0 ? (currentTime / duration) * 100 : 0;

  return (
    <div className={className} dir="ltr">
      {hasAudio && (
        <audio
          ref={audioRef}
          src={audioUrl}
          preload="metadata"
          crossOrigin="anonymous"
        />
      )}

      {/* Controls row */}
      <div className="flex items-center gap-2">
        {/* Skip back */}
        <Button
          variant="ghost"
          size="icon"
          className="w-8 h-8 text-muted-foreground hover:text-foreground"
          onClick={handleSkipBack}
          disabled={!hasAudio}
        >
          <SkipBack className="w-4 h-4" />
        </Button>

        {/* Play / Pause */}
        <Button
          size="icon"
          className="w-10 h-10 rounded-full bg-primary hover:bg-primary/80 shadow-lg shadow-primary/30"
          onClick={togglePlay}
          disabled={!hasAudio || error}
        >
          {loading ? (
            <span className="w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" />
          ) : isPlaying ? (
            <Pause className="w-4 h-4" />
          ) : (
            <Play className="w-4 h-4 ml-0.5" />
          )}
        </Button>

        {/* Time + Seek */}
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <span className="text-xs font-mono text-muted-foreground w-12 text-right shrink-0">
            {formatTime(currentTime)}
          </span>
          <Slider
            value={[seekPct]}
            min={0}
            max={100}
            step={0.1}
            onValueChange={handleSeek}
            disabled={!hasAudio || duration === 0}
            className="flex-1"
          />
          <span className="text-xs font-mono text-muted-foreground w-12 shrink-0">
            {duration > 0 ? formatTime(duration) : "--:--"}
          </span>
        </div>

        {/* Volume */}
        <Button
          variant="ghost"
          size="icon"
          className="w-8 h-8 text-muted-foreground hover:text-foreground shrink-0"
          onClick={handleMuteToggle}
        >
          {muted || volume === 0 ? (
            <VolumeX className="w-4 h-4" />
          ) : (
            <Volume2 className="w-4 h-4" />
          )}
        </Button>
        <Slider
          value={[muted ? 0 : Math.round(volume * 100)]}
          min={0}
          max={100}
          step={1}
          onValueChange={handleVolumeChange}
          className="w-20 shrink-0"
        />
      </div>

      {!hasAudio && (
        <p className="text-xs text-muted-foreground text-center mt-1">
          {t("Upload audio to enable playback")}
        </p>
      )}
      {error && hasAudio && (
        <p className="text-xs text-destructive text-center mt-1">
          {t("Audio playback error")}
        </p>
      )}
    </div>
  );
}
