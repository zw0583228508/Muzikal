import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Download, Loader2, CheckCircle2, FileMusic, Music2, FileText, Volume2, Disc3 } from "lucide-react";
import { useExportProject } from "@workspace/api-client-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { cn } from "@/lib/utils";

interface ExportFormat {
  id: string;
  label: string;
  icon: React.ReactNode;
  desc: string;
  group: "score" | "audio";
}

const EXPORT_FORMATS: ExportFormat[] = [
  { id: "midi",     label: "MIDI",          icon: <FileMusic className="w-5 h-5" />,  desc: "Multi-track .mid file",      group: "score" },
  { id: "musicxml", label: "MusicXML",      icon: <Music2 className="w-5 h-5" />,    desc: "Score notation / import",    group: "score" },
  { id: "pdf",      label: "Lead Sheet",    icon: <FileText className="w-5 h-5" />,  desc: "Printable chord chart PDF",  group: "score" },
  { id: "wav",      label: "WAV",           icon: <Volume2 className="w-5 h-5" />,   desc: "24-bit uncompressed",        group: "audio" },
  { id: "flac",     label: "FLAC",          icon: <Disc3 className="w-5 h-5" />,     desc: "Lossless compressed",        group: "audio" },
  { id: "mp3",      label: "MP3 320kbps",   icon: <Volume2 className="w-5 h-5" />,   desc: "Compressed, widely playable", group: "audio" },
  { id: "stems",    label: "Stems",         icon: <Disc3 className="w-5 h-5" />,     desc: "Per-instrument audio tracks", group: "audio" },
];

interface ExportCenterProps {
  projectId: number;
  hasArrangement: boolean;
}

export default function ExportCenter({ projectId, hasArrangement }: ExportCenterProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [selectedFormats, setSelectedFormats] = useState<string[]>([]);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);

  const filesKey = [`/api/projects/${projectId}/files`];
  const { data: files = [] } = useQuery<any[]>({
    queryKey: filesKey,
    queryFn: () => fetch(`/api/projects/${projectId}/files`).then(r => r.json()),
  });

  const exportMutation = useExportProject({
    mutation: {
      onSuccess: (data: any) => {
        setActiveJobId(data.jobId ?? null);
        queryClient.invalidateQueries({ queryKey: filesKey });
      },
    },
  });

  const [renderPending, setRenderPending] = useState(false);
  const handleRenderAudio = async (formats: string[]) => {
    setRenderPending(true);
    try {
      const res = await fetch(`/api/projects/${projectId}/render`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ formats }),
      });
      const data = await res.json();
      setActiveJobId(data.jobId ?? null);
      queryClient.invalidateQueries({ queryKey: filesKey });
    } finally {
      setRenderPending(false);
    }
  };

  const scoreFormats  = EXPORT_FORMATS.filter(f => f.group === "score");
  const audioFormats  = EXPORT_FORMATS.filter(f => f.group === "audio");
  const isLoading     = exportMutation.isPending || renderPending;

  const toggleFormat = (id: string) => {
    setSelectedFormats(prev =>
      prev.includes(id) ? prev.filter(f => f !== id) : [...prev, id]
    );
  };

  const handleExport = () => {
    if (!selectedFormats.length) return;
    const scoreSelected = selectedFormats.filter(f => ["midi","musicxml","pdf"].includes(f));
    const audioSelected = selectedFormats.filter(f => ["wav","flac","mp3","stems"].includes(f));

    if (scoreSelected.length) {
      exportMutation.mutate({ projectId, data: { formats: scoreSelected } });
    }
    if (audioSelected.length) {
      handleRenderAudio(audioSelected);
    }
  };

  const FormatCard = ({ fmt }: { fmt: ExportFormat }) => {
    const selected = selectedFormats.includes(fmt.id);
    return (
      <button
        onClick={() => toggleFormat(fmt.id)}
        className={cn(
          "w-full text-start p-3 rounded-lg border transition-all flex items-center gap-3",
          selected
            ? "border-primary bg-primary/10 text-primary"
            : "border-white/10 bg-white/5 hover:border-white/30 text-muted-foreground hover:text-white"
        )}
      >
        <div className={cn("flex-shrink-0", selected ? "text-primary" : "text-muted-foreground")}>
          {fmt.icon}
        </div>
        <div>
          <div className="font-medium text-sm">{fmt.label}</div>
          <div className="text-xs opacity-70">{fmt.desc}</div>
        </div>
        {selected && <CheckCircle2 className="w-4 h-4 ml-auto text-primary flex-shrink-0" />}
      </button>
    );
  };

  return (
    <div className="space-y-6 p-1">
      {!hasArrangement && (
        <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-400 text-sm">
          {t("Generate an arrangement first to enable audio export")}
        </div>
      )}

      <div className="space-y-4">
        <div>
          <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
            {t("Score & MIDI")}
          </h3>
          <div className="grid grid-cols-1 gap-2">
            {scoreFormats.map(fmt => <FormatCard key={fmt.id} fmt={fmt} />)}
          </div>
        </div>

        <div>
          <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
            {t("Audio Render")}
          </h3>
          <div className="grid grid-cols-1 gap-2">
            {audioFormats.map(fmt => (
              <div key={fmt.id} className={!hasArrangement ? "opacity-40 pointer-events-none" : ""}>
                <FormatCard fmt={fmt} />
              </div>
            ))}
          </div>
        </div>
      </div>

      <Button
        variant="glow"
        className="w-full"
        disabled={isLoading || selectedFormats.length === 0}
        onClick={handleExport}
      >
        {isLoading
          ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" />{t("Exporting...")}</>
          : <><Download className="w-4 h-4 mr-2" />{t("Export")} {selectedFormats.length > 0 ? `(${selectedFormats.length})` : ""}</>
        }
      </Button>

      {/* Downloads list */}
      {(files as any[]).length > 0 && (
        <div className="space-y-2">
          <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
            {t("Downloads")}
          </h3>
          <div className="space-y-1 max-h-48 overflow-y-auto">
            {(files as any[]).map((file: any) => (
              <div key={file.id ?? file.fileName} className="flex items-center justify-between p-2 rounded bg-white/5 text-sm">
                <div className="flex items-center gap-2 min-w-0">
                  <FileMusic className="w-4 h-4 text-muted-foreground flex-shrink-0" />
                  <span className="truncate text-white/80">{file.fileName}</span>
                  <Badge variant="outline" className="text-xs flex-shrink-0">{file.fileType?.toUpperCase()}</Badge>
                </div>
                <a
                  href={`/api/projects/${projectId}/files/${file.fileName}/download`}
                  download
                  className="flex-shrink-0 ml-2 text-primary hover:text-primary/80"
                >
                  <Download className="w-4 h-4" />
                </a>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
