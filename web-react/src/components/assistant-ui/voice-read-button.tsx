import { streamMessageSpeechUrl } from "@/api/tts";
import { LoaderCircleIcon, PauseIcon, PlayIcon, Volume2Icon } from "lucide-react";
import { useEffect, useRef, useState, type FC } from "react";


type VoiceState = "idle" | "loading" | "playing" | "paused" | "error";

type ActivePlayback = {
  audio: HTMLAudioElement;
  interrupt: () => void;
};

let activePlayback: ActivePlayback | null = null;
const PLAYBACK_START_TIMEOUT_MS = 15000;

export function hasSpeakableText(markdown: string): boolean {
  return markdown
    .replace(/```[\s\S]*?```|~~~[\s\S]*?~~~/g, "\n")
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/`([^`]*)`/g, "$1")
    .replace(/^\s{0,3}#{1,6}\s*/gm, "")
    .replace(/^\s*(?:[-+*]|\d+[.)])\s+/gm, "")
    .replace(/^\s*>+\s?/gm, "")
    .replace(/<[^>]+>/g, "")
    .replace(/[*_~]/g, "")
    .trim().length > 0;
}

export async function playWithTimeout(audio: HTMLAudioElement, timeoutMs = PLAYBACK_START_TIMEOUT_MS): Promise<void> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    await Promise.race([
      audio.play(),
      new Promise<never>((_, reject) => {
        timer = setTimeout(() => reject(new Error("音频已生成，但浏览器未开始播放，请再次点击播放")), timeoutMs);
      }),
    ]);
  } finally {
    if (timer !== undefined) clearTimeout(timer);
  }
}

export const VoiceReadButton: FC<{ sessionId: string; messageId: string }> = ({
  sessionId,
  messageId,
}) => {
  const [state, setState] = useState<VoiceState>("idle");
  const [error, setError] = useState("");
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      const audio = audioRef.current;
      if (audio) {
        audio.pause();
        audio.removeAttribute("src");
        audio.load();
      }
      if (activePlayback?.audio === audio) activePlayback = null;
    };
  }, []);

  const play = async (audio: HTMLAudioElement) => {
    if (activePlayback?.audio !== audio) activePlayback?.interrupt();
    activePlayback = {
      audio,
      interrupt: () => {
        audio.pause();
        if (mountedRef.current) setState("paused");
      },
    };
    try {
      await playWithTimeout(audio);
      if (mountedRef.current) setState("playing");
    } catch (caught) {
      if (activePlayback?.audio === audio) activePlayback = null;
      if (mountedRef.current) {
        const blocked = caught instanceof DOMException && caught.name === "NotAllowedError";
        setError(blocked ? "浏览器阻止了自动播放，请再次点击播放" : caught instanceof Error ? caught.message : "语音播放失败");
        setState(blocked ? "paused" : "error");
      }
    }
  };

  const handleClick = async () => {
    if (state === "loading") return;
    const existing = audioRef.current;
    if (state === "playing" && existing) {
      existing.pause();
      if (activePlayback?.audio === existing) activePlayback = null;
      setState("paused");
      return;
    }
    if (existing) {
      if (existing.ended) existing.currentTime = 0;
      await play(existing);
      return;
    }

    setState("loading");
    setError("");
    try {
      const audio = new Audio(streamMessageSpeechUrl(sessionId, messageId));
      audio.preload = "auto";
      audioRef.current = audio;
      audio.addEventListener("ended", () => {
        if (activePlayback?.audio === audio) activePlayback = null;
        if (mountedRef.current) setState("idle");
      });
      audio.addEventListener("error", () => {
        if (activePlayback?.audio === audio) activePlayback = null;
        if (mountedRef.current) {
          setError("语音流播放失败，请重试");
          setState("error");
        }
      });
      setState("paused");
      audio.load?.();
      await play(audio);
    } catch (caught) {
      if (mountedRef.current) {
        const timedOut = caught instanceof DOMException && caught.name === "AbortError";
        setError(timedOut ? "语音生成超时，请重试" : caught instanceof Error ? caught.message : "语音生成失败");
        setState("error");
      }
    }
  };

  const label = state === "loading"
    ? "正在生成语音"
    : state === "playing"
      ? "正在朗读"
      : state === "paused"
        ? "继续朗读"
        : state === "error"
          ? "重试语音"
          : "语音朗读";
  const Icon = state === "loading"
    ? LoaderCircleIcon
    : state === "playing"
      ? PauseIcon
      : state === "paused"
        ? PlayIcon
        : Volume2Icon;

  return (
    <button
      type="button"
      aria-label={label}
      title={error || label}
      disabled={state === "loading"}
      onClick={() => { void handleClick(); }}
      className="iris-voice-read-button mt-2 ml-2 inline-flex h-8 items-center gap-1.5 rounded-full border border-border/70 bg-background px-3 text-xs text-muted-foreground shadow-xs transition-colors hover:bg-muted hover:text-foreground disabled:cursor-wait disabled:opacity-70"
    >
      <Icon className={`size-3.5 ${state === "loading" ? "animate-spin" : ""}`} />
      <span>{label}</span>
    </button>
  );
};
