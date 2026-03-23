/**
 * useProjectStudio — encapsulates all state, data fetching, and event handlers
 * for the ProjectStudio page. Keeps project-studio.tsx as a thin orchestrator.
 */

import { useState, useRef, useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  useGetProject,
  useGetAnalysisResults,
  useGetArrangement,
  useUploadAudio,
  useStartAnalysis,
  useGenerateArrangement,
  useExportProject,
  useListStyles,
} from "@workspace/api-client-react";
import { useJobPolling } from "@/hooks/use-job-polling";
import { useJobWebSocket, type JobUpdate } from "@/hooks/use-job-websocket";

export function useProjectStudio(projectId: number) {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ─ Local UI state ──────────────────────────────────────────────────────────
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [activeJobIsMock, setActiveJobIsMock] = useState(false);
  const [jobFailedMsg, setJobFailedMsg] = useState<string | null>(null);
  const [showMockBanner, setShowMockBanner] = useState(false);
  const [showCorrections, setShowCorrections] = useState(false);
  const [selectedStyle, setSelectedStyle] = useState("pop");
  const [selectedPersona, setSelectedPersona] = useState<string | null>(null);
  const [selectedTrack, setSelectedTrack] = useState<any | null>(null);
  const [lockedFields, setLockedFields] = useState<Set<string>>(new Set());
  const [activeTab, setActiveTab] = useState("analysis");
  const [selectedFormats, setSelectedFormats] = useState<Record<string, boolean>>({
    midi: true, musicxml: false, pdf: false,
    wav: true, flac: false, mp3: false, stems: false,
  });
  const [editingChordIdx, setEditingChordIdx] = useState<number | null>(null);
  const [chordOverrides, setChordOverrides] = useState<Record<number, string>>({});

  // ─ Remote data ────────────────────────────────────────────────────────────
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

  const { data: modeData } = useQuery<{
    isMock: boolean;
    pipelineVersion?: string;
    modelVersions?: Record<string, string>;
  }>({
    queryKey: ["/api/projects/mock-mode"],
    queryFn: () => fetch("/api/projects/mock-mode").then(r => r.json()),
    staleTime: Infinity,
  });
  const isMockMode = modeData?.isMock ?? false;
  const modelVersions = modeData?.modelVersions ?? {};

  const { data: personas = [] } = useQuery<any[]>({
    queryKey: ["/api/styles/personas"],
    queryFn: () => fetch("/api/styles/personas").then(r => r.json()),
    staleTime: 5 * 60 * 1000,
  });

  // ─ Mutations ──────────────────────────────────────────────────────────────
  const uploadMut = useUploadAudio();
  const analyzeMut = useStartAnalysis();
  const arrangeMut = useGenerateArrangement();
  const exportMut = useExportProject();

  // ─ Derived helpers ────────────────────────────────────────────────────────
  const invalidateAll = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: [`/api/projects/${projectId}`] });
    queryClient.invalidateQueries({ queryKey: [`/api/projects/${projectId}/analysis`] });
    queryClient.invalidateQueries({ queryKey: [`/api/projects/${projectId}/arrangement`] });
    queryClient.invalidateQueries({ queryKey: filesQueryKey });
  }, [queryClient, projectId]);

  const onJobComplete = useCallback(() => {
    invalidateAll();
    setActiveJobId(null);
    setJobFailedMsg(null);
  }, [invalidateAll]);

  // ─ WebSocket (primary real-time updates) ──────────────────────────────────
  const { subscribeToJob } = useJobWebSocket({
    projectId,
    onJobUpdate: useCallback((update: JobUpdate) => {
      if (update.isMock) {
        setActiveJobIsMock(true);
        setShowMockBanner(true);
      }
      if (update.status === "completed") onJobComplete();
      if (update.status === "failed") {
        setJobFailedMsg(update.errorMessage || "Unknown error");
        setActiveJobId(null);
        setActiveJobIsMock(false);
      }
    }, [onJobComplete]),
  });

  // ─ Polling (fallback) ─────────────────────────────────────────────────────
  const { job: activeJob } = useJobPolling(activeJobId, onJobComplete);

  // ─ Job starter ────────────────────────────────────────────────────────────
  const startJob = useCallback((jobId: string) => {
    setActiveJobId(jobId);
    setActiveJobIsMock(false);
    setJobFailedMsg(null);
    subscribeToJob(jobId);
  }, [subscribeToJob]);

  // ─ Action handlers ────────────────────────────────────────────────────────
  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const res = await uploadMut.mutateAsync({ projectId, data: { file } });
      startJob(res.jobId);
      invalidateAll();
    } catch (err) {
      console.error(err);
    }
  };

  const handleAnalyze = async () => {
    try {
      const res = await analyzeMut.mutateAsync({ projectId });
      startJob(res.jobId);
    } catch (err) {
      console.error(err);
    }
  };

  const handleArrange = async () => {
    try {
      const res = await arrangeMut.mutateAsync({
        projectId,
        data: {
          styleId: selectedStyle,
          density: 0.8,
          humanize: true,
          lockedFields: Array.from(lockedFields),
          personaId: selectedPersona ?? undefined,
        },
      });
      startJob(res.jobId);
    } catch (err) {
      console.error(err);
    }
  };

  const handleRegenSection = async (sectionLabel: string) => {
    try {
      const res = await fetch(
        `/api/projects/${projectId}/arrangement/section/${encodeURIComponent(sectionLabel)}/regenerate`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ styleId: selectedStyle, personaId: selectedPersona }),
        }
      );
      const data = await res.json();
      if (data.jobId) startJob(data.jobId);
    } catch (err) { console.error(err); }
  };

  const handleRegenTrack = async (trackId: string) => {
    try {
      const res = await fetch(
        `/api/projects/${projectId}/arrangement/track/${encodeURIComponent(trackId)}/regenerate`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ styleId: selectedStyle, personaId: selectedPersona }),
        }
      );
      const data = await res.json();
      if (data.jobId) startJob(data.jobId);
    } catch (err) { console.error(err); }
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

  const toggleLock = useCallback((field: string) => {
    setLockedFields(prev => {
      const next = new Set(prev);
      if (next.has(field)) next.delete(field); else next.add(field);
      return next;
    });
  }, []);

  const handleSetChordOverride = useCallback((idx: number, chord: string) => {
    if (idx === -1) {
      setChordOverrides({});
    } else {
      setChordOverrides(prev => ({ ...prev, [idx]: chord }));
    }
  }, []);

  return {
    // refs
    fileInputRef,
    // project data
    project, isProjLoading,
    analysis, arrangement,
    styles, personas,
    projectFiles,
    isMockMode, modelVersions,
    // job state
    activeJobId, activeJobIsMock,
    activeJob, jobFailedMsg,
    // UI state
    showMockBanner, setShowMockBanner,
    showCorrections, setShowCorrections,
    selectedStyle, setSelectedStyle,
    selectedPersona, setSelectedPersona,
    selectedTrack, setSelectedTrack,
    lockedFields,
    activeTab, setActiveTab,
    selectedFormats, setSelectedFormats,
    editingChordIdx, setEditingChordIdx,
    chordOverrides,
    // actions
    handleUpload,
    handleAnalyze,
    handleArrange,
    handleRegenSection,
    handleRegenTrack,
    handleExport,
    handleRender,
    toggleLock,
    handleSetChordOverride,
    invalidateAll,
  };
}
