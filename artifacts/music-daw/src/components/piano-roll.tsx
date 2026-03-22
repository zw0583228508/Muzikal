import { useRef, useState, useMemo } from "react";
import { X, ZoomIn, ZoomOut, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { useTranslation } from "react-i18next";

// ─── Music theory helpers ─────────────────────────────────────────────────────
const BLACK_KEY_SEMITONES = new Set([1, 3, 6, 8, 10]);
const NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];

function isBlack(pitch: number) { return BLACK_KEY_SEMITONES.has(pitch % 12); }
function noteName(pitch: number) {
  return `${NOTE_NAMES[pitch % 12]}${Math.floor(pitch / 12) - 1}`;
}

// ─── Constants ────────────────────────────────────────────────────────────────
const KEY_H = 7;         // px per MIDI pitch row
const PIANO_W = 56;      // px — left keyboard column
const RULER_H = 28;      // px — top time ruler
const MIN_ZOOM = 20;     // px per beat
const MAX_ZOOM = 240;

// ─── Types ────────────────────────────────────────────────────────────────────
interface MidiNote { startTime: number; duration: number; pitch: number; velocity: number; }
interface Track {
  id: string;
  name: string;
  color: string;
  notes: MidiNote[];
  instrument?: string;
}

interface PianoRollProps {
  track: Track;
  bpm?: number;
  totalDurationSeconds?: number;
  onClose: () => void;
}

// ─── Component ────────────────────────────────────────────────────────────────
export function PianoRoll({ track, bpm = 120, totalDurationSeconds = 180, onClose }: PianoRollProps) {
  const { t } = useTranslation();
  const scrollRef = useRef<HTMLDivElement>(null);
  const [zoom, setZoom] = useState(50);            // px / beat
  const [selectedNote, setSelectedNote] = useState<MidiNote | null>(null);

  const beatDuration = 60 / bpm;
  const pxPerSec = zoom / beatDuration;
  const totalWidth = totalDurationSeconds * pxPerSec;

  // Pitch bounds — based on note content with generous padding
  const pitches = track.notes?.map(n => n.pitch) ?? [];
  const rawMin = pitches.length ? Math.min(...pitches) : 48;
  const rawMax = pitches.length ? Math.max(...pitches) : 84;
  const minPitch = Math.max(0, rawMin - 8);
  const maxPitch = Math.min(127, rawMax + 8);
  const numRows = maxPitch - minPitch + 1;
  const gridH = numRows * KEY_H;

  // Bar/beat grid
  const beats = useMemo(() => {
    const arr: number[] = [];
    for (let t = 0; t <= totalDurationSeconds; t += beatDuration) arr.push(t);
    return arr;
  }, [totalDurationSeconds, beatDuration]);

  const zoomPct = Math.round(zoom * 100 / 50);

  return (
    <div
      className="fixed inset-x-0 bottom-0 z-50 flex flex-col bg-[#090910] border-t-2 shadow-[0_-4px_40px_rgba(0,0,0,0.8)]"
      style={{ height: 340, borderColor: track.color || "#00f0ff" }}
    >
      {/* ── Header ── */}
      <div className="flex-shrink-0 flex items-center justify-between px-4 h-10 border-b border-white/10 bg-black/50 gap-4">
        {/* Track info */}
        <div className="flex items-center gap-3 min-w-0">
          <button onClick={onClose} className="hover:text-white/60 text-muted-foreground">
            <ChevronDown className="w-4 h-4" />
          </button>
          <div className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: track.color || "#00f0ff" }} />
          <span className="text-sm font-bold text-white truncate">{t(track.name)}</span>
          <span className="text-xs text-muted-foreground flex-shrink-0">{track.notes?.length ?? 0} {t("notes")}</span>
        </div>

        {/* Selected note info */}
        {selectedNote && (
          <div className="text-xs bg-white/5 border border-white/10 rounded px-2 py-0.5 font-mono flex-shrink-0" dir="ltr">
            <span className="text-primary">{noteName(selectedNote.pitch)}</span>
            <span className="text-muted-foreground mx-1">·</span>
            <span className="text-white/70">vel {selectedNote.velocity}</span>
            <span className="text-muted-foreground mx-1">·</span>
            <span className="text-white/70">{selectedNote.duration.toFixed(2)}s</span>
          </div>
        )}

        {/* Controls */}
        <div className="flex items-center gap-2 flex-shrink-0">
          <span className="text-xs text-muted-foreground" dir="ltr">{bpm} BPM</span>
          <div className="flex items-center gap-1 bg-black/30 rounded p-0.5" dir="ltr">
            <button
              onClick={() => setZoom(z => Math.max(MIN_ZOOM, z - 15))}
              className="w-6 h-6 rounded hover:bg-white/10 flex items-center justify-center text-muted-foreground hover:text-white"
            ><ZoomOut className="w-3 h-3" /></button>
            <span className="text-[11px] text-muted-foreground w-9 text-center">{zoomPct}%</span>
            <button
              onClick={() => setZoom(z => Math.min(MAX_ZOOM, z + 15))}
              className="w-6 h-6 rounded hover:bg-white/10 flex items-center justify-center text-muted-foreground hover:text-white"
            ><ZoomIn className="w-3 h-3" /></button>
          </div>
          <button
            onClick={onClose}
            className="w-7 h-7 rounded hover:bg-red-500/20 flex items-center justify-center text-muted-foreground hover:text-red-400"
          ><X className="w-4 h-4" /></button>
        </div>
      </div>

      {/* ── Body ── */}
      <div className="flex flex-1 overflow-hidden">

        {/* Piano keyboard */}
        <div className="flex-shrink-0 flex flex-col" style={{ width: PIANO_W }}>
          <div className="flex-shrink-0 bg-black/60 border-b border-white/10" style={{ height: RULER_H }} />
          <div className="flex-1 overflow-hidden relative">
            <div className="absolute inset-0 overflow-hidden" style={{ height: gridH }}>
              {Array.from({ length: numRows }, (_, i) => {
                const pitch = maxPitch - i;
                const black = isBlack(pitch);
                const isCnote = pitch % 12 === 0;
                return (
                  <div
                    key={pitch}
                    style={{ height: KEY_H, top: i * KEY_H }}
                    className={cn(
                      "absolute w-full flex items-center text-[8px] select-none border-b",
                      black ? "bg-[#181820] border-black/50" : "bg-[#252530] border-black/30",
                      isCnote && "border-b border-white/15"
                    )}
                  >
                    {isCnote && (
                      <span
                        className="text-[9px] text-white/40 font-mono leading-none"
                        style={{ paddingLeft: 3 }}
                      >
                        {noteName(pitch)}
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* Scrollable grid + notes */}
        <div ref={scrollRef} className="flex-1 overflow-auto" dir="ltr">
          <div
            style={{
              position: "relative",
              width: Math.max(totalWidth + 60, 400),
              height: gridH + RULER_H,
            }}
          >
            {/* Time ruler (sticky) */}
            <div
              className="sticky top-0 left-0 right-0 z-20 bg-[#090910] border-b border-white/10 overflow-hidden"
              style={{ height: RULER_H, width: Math.max(totalWidth + 60, 400) }}
            >
              {beats.filter((_, i) => i % 4 === 0).map((bt, barIdx) => (
                <div
                  key={bt}
                  className="absolute text-[10px] text-muted-foreground border-l border-white/20 pl-1 flex items-end pb-1"
                  style={{ left: bt * pxPerSec, top: 0, height: RULER_H }}
                >
                  {barIdx * 4 + 1}
                </div>
              ))}
              {beats.map((bt, i) => (
                <div
                  key={i}
                  className="absolute top-0 bottom-0"
                  style={{
                    left: bt * pxPerSec,
                    width: 1,
                    backgroundColor: i % 4 === 0 ? "rgba(255,255,255,0.14)" : "rgba(255,255,255,0.04)",
                  }}
                />
              ))}
            </div>

            {/* Pitch row backgrounds */}
            {Array.from({ length: numRows }, (_, i) => {
              const pitch = maxPitch - i;
              const black = isBlack(pitch);
              const isCnote = pitch % 12 === 0;
              return (
                <div
                  key={pitch}
                  style={{
                    position: "absolute",
                    top: RULER_H + i * KEY_H,
                    left: 0,
                    right: 0,
                    height: KEY_H,
                    backgroundColor: black ? "#0d0d14" : "#111118",
                    borderBottom: isCnote ? "1px solid rgba(255,255,255,0.08)" : "1px solid rgba(0,0,0,0.3)",
                  }}
                />
              );
            })}

            {/* Beat grid lines (over rows, under notes) */}
            {beats.map((bt, i) => (
              <div
                key={i}
                style={{
                  position: "absolute",
                  left: bt * pxPerSec,
                  top: RULER_H,
                  height: gridH,
                  width: 1,
                  backgroundColor: i % 4 === 0
                    ? "rgba(255,255,255,0.10)"
                    : i % 2 === 0
                    ? "rgba(255,255,255,0.04)"
                    : "rgba(255,255,255,0.02)",
                }}
              />
            ))}

            {/* MIDI notes */}
            {track.notes?.map((note, idx) => {
              const rowIdx = maxPitch - note.pitch;
              if (rowIdx < 0 || rowIdx >= numRows) return null;
              const x = note.startTime * pxPerSec;
              const w = Math.max(note.duration * pxPerSec, 3);
              const y = RULER_H + rowIdx * KEY_H + 1;
              const h = KEY_H - 2;
              const isSelected = selectedNote === note;

              return (
                <div
                  key={idx}
                  onClick={() => setSelectedNote(isSelected ? null : note)}
                  style={{
                    position: "absolute",
                    left: x,
                    top: y,
                    width: w,
                    height: h,
                    backgroundColor: track.color || "#00f0ff",
                    opacity: isSelected ? 1 : 0.55 + (note.velocity / 127) * 0.45,
                    borderRadius: 2,
                    cursor: "pointer",
                    outline: isSelected ? "1.5px solid white" : undefined,
                    boxShadow: isSelected ? `0 0 8px ${track.color || "#00f0ff"}` : undefined,
                  }}
                  title={`${noteName(note.pitch)} vel:${note.velocity} dur:${note.duration.toFixed(2)}s`}
                />
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
