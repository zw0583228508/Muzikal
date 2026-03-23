import { useEffect, useRef, useState, useCallback } from "react";
import * as Tone from "tone";
import Soundfont from "soundfont-player";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { Play, Pause, Square, Volume2, VolumeX, Music2, Loader2 } from "lucide-react";
import { cn, formatTime } from "@/lib/utils";

// ─── GM Program → Soundfont instrument name ──────────────────────────────────
const GM_PROGRAM_MAP: Record<number, string> = {
  0: "acoustic_grand_piano", 1: "bright_acoustic_piano", 4: "electric_piano_1",
  6: "harpsichord", 11: "vibraphone", 12: "marimba", 13: "xylophone",
  17: "percussive_organ", 19: "church_organ", 21: "accordion",
  24: "acoustic_guitar_nylon", 25: "acoustic_guitar_steel",
  26: "electric_guitar_jazz", 30: "distortion_guitar",
  32: "acoustic_bass", 33: "electric_bass_finger", 38: "synth_bass_1",
  40: "violin", 41: "viola", 42: "cello", 43: "contrabass",
  46: "orchestral_harp", 47: "timpani",
  48: "string_ensemble_1", 49: "string_ensemble_2",
  56: "trumpet", 57: "trombone", 58: "tuba", 60: "french_horn",
  61: "brass_section", 64: "soprano_sax", 65: "alto_sax",
  66: "tenor_sax", 67: "baritone_sax",
  68: "oboe", 69: "english_horn", 71: "clarinet", 73: "flute",
  74: "recorder", 75: "pan_flute",
  105: "banjo", 106: "shamisen",
  112: "tinkle_bell", 113: "agogo", 115: "woodblock",
  116: "taiko_drum", 117: "melodic_tom", 118: "synth_drum",
};

// Canonical instrument name → GM program fallback
const INSTRUMENT_FALLBACK: Record<string, number> = {
  piano: 0, strings: 48, brass: 56, trumpet: 56, trombone: 57, tuba: 58,
  french_horn: 60, clarinet: 71, flute: 73, oboe: 68,
  violin: 40, cello: 42, bass: 32, "double_bass": 43,
  guitar: 25, accordion: 21, harp: 46,
  drums: 0, percussion: 112, vibraphone: 11,
  choir: 52, nay: 75, oud: 105, saz: 105, darbuka: 116,
};

function getInstrumentName(track: TrackData): string {
  const prog = track.midiProgram;
  if (prog != null && GM_PROGRAM_MAP[prog]) return GM_PROGRAM_MAP[prog];
  const name = track.instrument?.toLowerCase() ?? "";
  for (const [key, fallbackProg] of Object.entries(INSTRUMENT_FALLBACK)) {
    if (name.includes(key)) {
      return GM_PROGRAM_MAP[fallbackProg] ?? "acoustic_grand_piano";
    }
  }
  return "acoustic_grand_piano";
}

// ─── MIDI note number → note name ────────────────────────────────────────────
const NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
function midiToNote(midi: number): string {
  const octave = Math.floor(midi / 12) - 1;
  return `${NOTE_NAMES[midi % 12]}${octave}`;
}

// ─── Types ────────────────────────────────────────────────────────────────────
interface NoteEvent {
  startTime: number;
  duration: number;
  pitch: number;
  velocity?: number;
}

interface TrackData {
  id: string;
  instrument?: string;
  midiProgram?: number;
  notes?: NoteEvent[];
  volume?: number;
}

interface MidiPlayerProps {
  tracks: TrackData[];
  totalDuration?: number;
  className?: string;
}

interface TrackState {
  muted: boolean;
  soloed: boolean;
  volume: number;
}

// ─── Component ────────────────────────────────────────────────────────────────
export function MidiPlayer({ tracks, totalDuration, className }: MidiPlayerProps) {
  const [loading, setLoading] = useState(false);
  const [loadProgress, setLoadProgress] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [masterVolume, setMasterVolume] = useState(85);
  const [trackStates, setTrackStates] = useState<Record<string, TrackState>>({});
  const [error, setError] = useState<string | null>(null);

  const acRef = useRef<AudioContext | null>(null);
  const instrumentsRef = useRef<Record<string, any>>({});
  const scheduledRef = useRef<any[]>([]);
  const startTimeRef = useRef<number>(0);
  const rafRef = useRef<number>(0);
  const pauseOffsetRef = useRef<number>(0);

  // Compute total duration from tracks if not provided
  const duration = totalDuration ?? Math.max(0, ...tracks.flatMap(t =>
    (t.notes ?? []).map(n => n.startTime + n.duration)
  ));

  // Init track states
  useEffect(() => {
    setTrackStates(prev => {
      const next: Record<string, TrackState> = {};
      for (const t of tracks) {
        next[t.id] = prev[t.id] ?? { muted: false, soloed: false, volume: t.volume ?? 80 };
      }
      return next;
    });
  }, [tracks]);

  const hasSoloed = Object.values(trackStates).some(s => s.soloed);

  const loadInstruments = useCallback(async () => {
    if (!tracks.length) return;
    setLoading(true);
    setError(null);
    setLoadProgress(0);

    try {
      if (!acRef.current) {
        acRef.current = new AudioContext();
      }
      const ac = acRef.current;
      const needed = [...new Set(tracks.map(t => getInstrumentName(t)))];
      let done = 0;

      await Promise.all(needed.map(async (name) => {
        if (instrumentsRef.current[name]) { done++; return; }
        try {
          instrumentsRef.current[name] = await Soundfont.instrument(ac, name as any, {
            soundfont: "MusyngKite",
            gain: 2,
          });
        } catch {
          // Fallback to piano
          instrumentsRef.current[name] = await Soundfont.instrument(ac, "acoustic_grand_piano" as any, {
            soundfont: "MusyngKite",
            gain: 2,
          });
        }
        done++;
        setLoadProgress(Math.round((done / needed.length) * 100));
      }));

      setLoading(false);
    } catch (e: any) {
      setError(e.message ?? "שגיאה בטעינת כלים");
      setLoading(false);
    }
  }, [tracks]);

  useEffect(() => {
    loadInstruments();
    return () => { stopPlayback(); };
  }, [loadInstruments]);

  const stopPlayback = useCallback(() => {
    for (const node of scheduledRef.current) {
      try { node.stop?.(); } catch {}
    }
    scheduledRef.current = [];
    cancelAnimationFrame(rafRef.current);
    setIsPlaying(false);
  }, []);

  const startPlayback = useCallback((fromOffset = 0) => {
    if (!acRef.current) return;
    stopPlayback();

    const ac = acRef.current;
    if (ac.state === "suspended") ac.resume();

    const now = ac.currentTime;
    startTimeRef.current = now - fromOffset;
    const gainFactor = masterVolume / 100;

    for (const track of tracks) {
      const ts = trackStates[track.id];
      if (!ts) continue;
      const isActive = ts.soloed || (!hasSoloed && !ts.muted);
      if (!isActive) continue;
      const trackGain = (ts.volume / 100) * gainFactor;

      const instrName = getInstrumentName(track);
      const instr = instrumentsRef.current[instrName] ?? instrumentsRef.current["acoustic_grand_piano"];
      if (!instr) continue;

      for (const note of track.notes ?? []) {
        if (note.startTime < fromOffset) continue;
        const when = now + (note.startTime - fromOffset);
        const noteName = midiToNote(note.pitch);
        const vel = (note.velocity ?? 80) / 127;
        try {
          const node = instr.play(noteName, when, {
            duration: note.duration,
            gain: trackGain * vel,
          });
          if (node) scheduledRef.current.push(node);
        } catch {}
      }
    }

    setIsPlaying(true);

    const tick = () => {
      if (!acRef.current) return;
      const elapsed = acRef.current.currentTime - startTimeRef.current;
      setCurrentTime(Math.min(elapsed, duration));
      if (elapsed >= duration) {
        stopPlayback();
        setCurrentTime(duration);
        pauseOffsetRef.current = 0;
        return;
      }
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
  }, [tracks, trackStates, hasSoloed, masterVolume, duration, stopPlayback]);

  const handlePlayPause = () => {
    if (isPlaying) {
      pauseOffsetRef.current = currentTime;
      stopPlayback();
    } else {
      startPlayback(pauseOffsetRef.current);
    }
  };

  const handleStop = () => {
    stopPlayback();
    pauseOffsetRef.current = 0;
    setCurrentTime(0);
  };

  const toggleMute = (id: string) => {
    setTrackStates(prev => ({
      ...prev,
      [id]: { ...prev[id], muted: !prev[id]?.muted },
    }));
  };

  const toggleSolo = (id: string) => {
    setTrackStates(prev => ({
      ...prev,
      [id]: { ...prev[id], soloed: !prev[id]?.soloed },
    }));
  };

  const progress = duration > 0 ? (currentTime / duration) * 100 : 0;

  if (!tracks.length) {
    return (
      <div className={cn("flex items-center justify-center h-24 text-sm text-muted-foreground", className)}>
        <Music2 className="w-5 h-5 mr-2 opacity-40" /> אין טראקים לניגון
      </div>
    );
  }

  return (
    <div className={cn("flex flex-col gap-3", className)} dir="ltr">
      {/* Progress bar */}
      <div className="relative h-1.5 bg-white/10 rounded-full overflow-hidden cursor-pointer"
        onClick={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          const ratio = (e.clientX - rect.left) / rect.width;
          const newTime = ratio * duration;
          pauseOffsetRef.current = newTime;
          setCurrentTime(newTime);
          if (isPlaying) { stopPlayback(); startPlayback(newTime); }
        }}
      >
        <div
          className="absolute inset-y-0 left-0 bg-gradient-to-r from-primary to-accent rounded-full transition-none"
          style={{ width: `${progress}%` }}
        />
      </div>

      {/* Time */}
      <div className="flex items-center justify-between text-[11px] font-mono text-muted-foreground tabular-nums -mt-1">
        <span>{formatTime(currentTime)}</span>
        <span>{formatTime(duration)}</span>
      </div>

      {/* Main controls */}
      <div className="flex items-center gap-3">
        {loading ? (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="w-4 h-4 animate-spin" />
            טוען כלים... {loadProgress}%
          </div>
        ) : (
          <div className="flex items-center gap-1">
            <Button size="icon" variant="ghost" className="h-8 w-8" onClick={handleStop} disabled={loading}>
              <Square className="w-3.5 h-3.5" />
            </Button>
            <Button
              size="icon"
              className="h-9 w-9 rounded-full bg-primary/20 hover:bg-primary/30 text-primary border border-primary/30"
              onClick={handlePlayPause}
              disabled={loading}
            >
              {isPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4 ml-0.5" />}
            </Button>
          </div>
        )}

        {error && <span className="text-xs text-destructive">{error}</span>}

        <div className="flex items-center gap-1.5 ml-auto w-28">
          <Volume2 className="w-3 h-3 text-muted-foreground shrink-0" />
          <Slider
            value={[masterVolume]}
            onValueChange={([v]) => setMasterVolume(v)}
            min={0} max={100}
            className="h-1"
          />
        </div>
      </div>

      {/* Track mixer */}
      <div className="space-y-1.5 max-h-48 overflow-y-auto custom-scrollbar pr-1">
        {tracks.map((track) => {
          const ts = trackStates[track.id] ?? { muted: false, soloed: false, volume: 80 };
          const isActive = ts.soloed || (!hasSoloed && !ts.muted);
          return (
            <div
              key={track.id}
              className={cn(
                "flex items-center gap-2 px-2 py-1.5 rounded-md border transition-all text-xs",
                isActive ? "border-white/10 bg-white/5" : "border-white/5 bg-black/20 opacity-50"
              )}
            >
              <div className="w-3 h-3 rounded-full bg-primary/40 shrink-0" />
              <span className="flex-1 font-medium text-white/80 truncate capitalize">
                {track.instrument ?? `Track ${track.id}`}
              </span>
              <button
                onClick={() => toggleSolo(track.id)}
                className={cn(
                  "px-1.5 py-0.5 rounded text-[9px] font-bold uppercase transition-colors",
                  ts.soloed ? "bg-accent/30 text-accent" : "bg-white/5 text-white/40 hover:text-white/70"
                )}
              >S</button>
              <button
                onClick={() => toggleMute(track.id)}
                className={cn(
                  "px-1.5 py-0.5 rounded text-[9px] font-bold uppercase transition-colors",
                  ts.muted ? "bg-destructive/30 text-destructive" : "bg-white/5 text-white/40 hover:text-white/70"
                )}
              >M</button>
              <div className="w-16">
                <Slider
                  value={[ts.volume]}
                  onValueChange={([v]) => setTrackStates(prev => ({
                    ...prev,
                    [track.id]: { ...prev[track.id], volume: v },
                  }))}
                  min={0} max={100}
                  className="h-1"
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
