import { useState, useRef, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { Send, Loader2, Bot, User, CheckCircle2, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import StyleProfileCard from "./style-profile-card";

interface Message {
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
}

interface AgentResponseData {
  type: "question" | "ready" | "error";
  text?: string;
  profile?: Record<string, unknown>;
  phase: string;
  session_id: string;
  collected_params: Record<string, unknown>;
}

interface ChatAgentProps {
  projectId: string;
  onProfileReady?: (profile: Record<string, unknown>) => void;
  className?: string;
}

const WELCOME_MESSAGE =
  "שלום! אני סוכן Muzikal. ספר לי — איזה סגנון מוזיקה אתה מחפש לעיבוד שלך? (קלזמר, בוסה נובה, פלמנקו, מזרחי, ג'אז ואלפי ז'אנרים נוספים)";

export default function ChatAgent({ projectId, onProfileReady, className }: ChatAgentProps) {
  const { i18n } = useTranslation();
  const isHebrew = i18n.language === "he";

  const [messages, setMessages] = useState<Message[]>([
    { role: "assistant", content: WELCOME_MESSAGE, timestamp: new Date() },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [phase, setPhase] = useState<string>("DISCOVERY");
  const [profile, setProfile] = useState<Record<string, unknown> | null>(null);
  const [confirming, setConfirming] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function sendMessage() {
    const text = input.trim();
    if (!text || loading) return;

    const userMsg: Message = { role: "user", content: text, timestamp: new Date() };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    try {
      const res = await fetch("/api/agent/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: text,
          projectId,
          sessionId,
        }),
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: AgentResponseData = await res.json();

      if (data.session_id) setSessionId(data.session_id);
      if (data.phase) setPhase(data.phase);

      if (data.type === "ready" && data.profile) {
        setProfile(data.profile);
        const assistantMsg: Message = {
          role: "assistant",
          content: "מצוין! בניתי את פרופיל הסגנון שלך. אתה יכול לבדוק אותו ולאשר את העיבוד.",
          timestamp: new Date(),
        };
        setMessages((prev) => [...prev, assistantMsg]);
      } else if (data.type === "question" && data.text) {
        const assistantMsg: Message = {
          role: "assistant",
          content: data.text,
          timestamp: new Date(),
        };
        setMessages((prev) => [...prev, assistantMsg]);
      } else if (data.type === "error" && data.text) {
        const errMsg: Message = {
          role: "assistant",
          content: `שגיאה: ${data.text}`,
          timestamp: new Date(),
        };
        setMessages((prev) => [...prev, errMsg]);
      }
    } catch (err) {
      const errMsg: Message = {
        role: "assistant",
        content: "שגיאה בתקשורת עם השרת. אנא נסה שוב.",
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errMsg]);
    } finally {
      setLoading(false);
    }
  }

  async function confirmProfile() {
    if (!sessionId || !profile) return;
    setConfirming(true);
    try {
      // שלב א: אישור הפרופיל בסוכן
      const confirmRes = await fetch("/api/agent/confirm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, project_id: projectId }),
      });
      if (!confirmRes.ok) throw new Error(`Confirm HTTP ${confirmRes.status}`);
      const confirmData = await confirmRes.json();

      if (!confirmData.confirmed) {
        throw new Error("Profile not confirmed by server");
      }

      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "הפרופיל אושר! מפעיל את מנוע העיבוד...", timestamp: new Date() },
      ]);

      // שלב ב: הפעלת arrangement עם StyleProfile
      const arrangeRes = await fetch(`/api/projects/${projectId}/arrangement`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          styleId: (confirmData.profile as Record<string, unknown>)?.genre ?? "pop",
          styleProfile: confirmData.profile,
        }),
      });

      if (arrangeRes.ok) {
        const arrangeData = await arrangeRes.json();
        const jobId: string = arrangeData.jobId ?? "—";
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: `העיבוד התחיל! מזהה משרה: ${jobId}. עבור לטאב "עיבוד" לעקוב אחר ההתקדמות.`,
            timestamp: new Date(),
          },
        ]);
        if (onProfileReady) onProfileReady(confirmData.profile);
      } else {
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: "הפרופיל אושר. לחץ על 'עיבוד' להמשך.", timestamp: new Date() },
        ]);
        if (onProfileReady) onProfileReady(confirmData.profile);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "שגיאה לא ידועה";
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `שגיאה באישור הפרופיל: ${msg}`, timestamp: new Date() },
      ]);
    } finally {
      setConfirming(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }

  const phaseLabels: Record<string, string> = {
    DISCOVERY: "שלב גילוי",
    ENRICHMENT: "העשרת מידע",
    EXECUTION: "מוכן לעיבוד",
  };

  return (
    <div className={cn("flex flex-col h-full bg-zinc-950 rounded-xl border border-zinc-800", className)} dir="rtl">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-zinc-800">
        <div className="w-8 h-8 rounded-full bg-indigo-600 flex items-center justify-center">
          <Sparkles className="w-4 h-4 text-white" />
        </div>
        <div>
          <div className="text-sm font-semibold text-white">סוכן מוזיקל</div>
          <div className="text-xs text-zinc-400">{phaseLabels[phase] ?? phase}</div>
        </div>
        <div className="mr-auto flex items-center gap-1">
          <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          <span className="text-xs text-zinc-400">פעיל</span>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3 min-h-0">
        {messages.map((msg, i) => (
          <div
            key={i}
            className={cn("flex gap-2", msg.role === "user" ? "flex-row-reverse" : "flex-row")}
          >
            <div
              className={cn(
                "w-7 h-7 rounded-full flex items-center justify-center shrink-0",
                msg.role === "user" ? "bg-blue-600" : "bg-indigo-600",
              )}
            >
              {msg.role === "user" ? (
                <User className="w-3.5 h-3.5 text-white" />
              ) : (
                <Bot className="w-3.5 h-3.5 text-white" />
              )}
            </div>
            <div
              className={cn(
                "max-w-[80%] px-3 py-2 rounded-2xl text-sm leading-relaxed",
                msg.role === "user"
                  ? "bg-blue-600/20 text-blue-100 rounded-tr-sm"
                  : "bg-zinc-800 text-zinc-200 rounded-tl-sm",
              )}
            >
              {msg.content}
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex gap-2">
            <div className="w-7 h-7 rounded-full bg-indigo-600 flex items-center justify-center shrink-0">
              <Bot className="w-3.5 h-3.5 text-white" />
            </div>
            <div className="bg-zinc-800 px-3 py-2 rounded-2xl rounded-tl-sm">
              <Loader2 className="w-4 h-4 animate-spin text-indigo-400" />
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Profile Card — shown when profile is ready */}
      {profile && (
        <div className="px-4 pb-3">
          <StyleProfileCard
            profile={profile}
            onConfirm={confirmProfile}
            confirming={confirming}
          />
        </div>
      )}

      {/* Input */}
      {!profile && (
        <div className="p-3 border-t border-zinc-800">
          <div className="flex gap-2">
            <Textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="תאר את הסגנון המוזיקלי שאתה מחפש..."
              className="resize-none min-h-[44px] max-h-[120px] bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-500 text-sm"
              rows={1}
              dir="rtl"
            />
            <Button
              onClick={sendMessage}
              disabled={loading || !input.trim()}
              size="sm"
              className="bg-indigo-600 hover:bg-indigo-500 shrink-0 self-end"
            >
              {loading ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Send className="w-4 h-4" />
              )}
            </Button>
          </div>
          <p className="text-xs text-zinc-600 mt-1 text-center">Enter לשליחה • Shift+Enter לשורה חדשה</p>
        </div>
      )}
    </div>
  );
}
