import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { AnalysisInspector } from "@/components/analysis-inspector";

const MOCK_ANALYSIS = {
  duration: 183.4,
  sampleRate: 22050,
  fileHash: "abc123def456",
  cacheEnabled: true,
  cacheHitCount: 5,
  rhythm: {
    bpm: 120,
    timeSignature: { numerator: 4, denominator: 4 },
    confidence: 0.91,
    beatGrid: [],
    downbeats: [],
    warnings: [],
  },
  key: { key: "D", globalKey: "D", mode: "minor", confidence: 0.88, modulations: [], alternatives: [] },
  chords: { chords: [], leadSheet: "Dm - Am - Gm - A", confidence: 0.75 },
  melody: { notes: [], inferredHarmony: [], confidence: 0.82 },
  vocals: { notes: [], phrases: [], confidence: 0.7 },
  structure: {
    sections: [
      { label: "intro", startTime: 0, endTime: 8, confidence: 0.9 },
      { label: "verse", startTime: 8, endTime: 48, confidence: 0.85 },
      { label: "chorus", startTime: 48, endTime: 72, confidence: 0.92 },
    ],
  },
  confidenceData: {
    overall: 0.84,
    rhythm: 0.91,
    key: 0.88,
    chords: 0.75,
    melody: 0.82,
    structure: 0.89,
    vocals: 0.7,
  },
  waveformData: [],
  sourceSeparation: { method: "hpss", stems: ["vocals", "accompaniment"], qualityScores: {}, warnings: [] },
  warnings: [],
  modelVersions: {
    rhythm: "madmom-0.16.1",
    key: "essentia-2.1b6",
    chords: "chord-cnn-0.4.0",
    melody: "pyin-0.1.1",
    structure: "msaf-0.5.0",
  },
};

describe("AnalysisInspector component", () => {
  it("renders without crashing when analysis data is provided", () => {
    const { container } = render(<AnalysisInspector analysis={MOCK_ANALYSIS} />);
    expect(container.firstChild).not.toBeNull();
  });

  it("shows BPM value from analysis", () => {
    render(<AnalysisInspector analysis={MOCK_ANALYSIS} />);
    expect(screen.getByText(/120/)).toBeInTheDocument();
  });

  it("shows detected key", () => {
    render(<AnalysisInspector analysis={MOCK_ANALYSIS} />);
    expect(screen.getByText(/D/)).toBeInTheDocument();
  });

  it("renders confidence scores section", () => {
    render(<AnalysisInspector analysis={MOCK_ANALYSIS} />);
    const pctElements = screen.getAllByText(/\d+%/);
    expect(pctElements.length).toBeGreaterThan(0);
  });

  it("shows all three sections in structure", () => {
    render(<AnalysisInspector analysis={MOCK_ANALYSIS} />);
    expect(screen.getAllByText(/intro/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/verse/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/chorus/i).length).toBeGreaterThan(0);
  });

  it("renders correctly with empty analysis object", () => {
    const { container } = render(<AnalysisInspector analysis={{}} />);
    expect(container.firstChild).not.toBeNull();
  });

  it("renders correctly with null analysis", () => {
    const { container } = render(<AnalysisInspector analysis={null} />);
    expect(container).toBeDefined();
  });
});
