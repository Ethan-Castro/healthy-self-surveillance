import { useEffect, useRef, useState } from "react";
import { fetchSessions } from "./api";
import type { AnalysisMode, FocusLabel, SessionSnapshot } from "./types";

const ORB_IMAGES_KEY = (label: FocusLabel) => `focus-buddy-orb-images-${label}`;

function loadOrbImages(label: FocusLabel): string[] {
  try {
    const raw = window.localStorage.getItem(ORB_IMAGES_KEY(label));
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    return Array.isArray(parsed) ? (parsed as string[]) : [];
  } catch {
    return [];
  }
}

const POLL_MS = 250;

function displayLabel(label: SessionSnapshot["current_label"], analysisMode: AnalysisMode): string {
  if (analysisMode === "classification") {
    return label === "focused" ? "Focused" : "Unfocused";
  }
  return label.charAt(0).toUpperCase() + label.slice(1);
}

export default function BubbleApp() {
  const [session, setSession] = useState<SessionSnapshot | null>(null);
  const [showNote, setShowNote] = useState(false);
  const [orbImages, setOrbImages] = useState<Record<FocusLabel, string[]>>(() => ({
    focused: loadOrbImages("focused"),
    drifting: loadOrbImages("drifting"),
    distracted: loadOrbImages("distracted"),
    away: loadOrbImages("away"),
  }));
  const cycleIndexRef = useRef<Record<FocusLabel, number>>({
    focused: 0,
    drifting: 0,
    distracted: 0,
    away: 0,
  });

  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (!e.key?.startsWith("focus-buddy-orb-images-")) return;
      const label = e.key.replace("focus-buddy-orb-images-", "") as FocusLabel;
      const images = loadOrbImages(label);
      cycleIndexRef.current[label] = 0;
      setOrbImages((prev) => ({ ...prev, [label]: images }));
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  useEffect(() => {
    const checkStatus = async () => {
      try {
        const sessions = await fetchSessions();
        const running = sessions.find((s) => s.status === "running");
        setSession(running ?? null);
      } catch {
        // Silent fail for the bubble
      }
    };

    void checkStatus();
    const interval = setInterval(checkStatus, POLL_MS);
    return () => clearInterval(interval);
  }, []);

  const label = session?.current_label ?? "away";
  const analysisMode = session?.analysis_mode ?? "annotation";
  const bubbleCopy = displayLabel(label, analysisMode);
  const reason = session?.short_reason ?? null;
  const companionMessage = session?.companion_message ?? null;

  const orbImageStyle: React.CSSProperties = (() => {
    const images = orbImages[label];
    if (!images.length) return {};
    const idx = cycleIndexRef.current[label] % images.length;
    return {
      backgroundImage: `url(${images[idx]})`,
      backgroundSize: "cover",
      backgroundPosition: "center",
    };
  })();

  return (
    <div className="bubble-container">
      <div className={`bubble-orb label-${label}`} style={orbImageStyle}>
        <div className="bubble-eye left" />
        <div className="bubble-eye right" />
        {label === "distracted" || label === "drifting" ? (
           <div className="bubble-mouth-frown" />
        ) : (
           <div className="bubble-mouth-smile" />
        )}
      </div>
      <span
        className="bubble-caption bubble-caption-clickable"
        style={{ WebkitAppRegion: "no-drag" } as React.CSSProperties}
        onClick={() => setShowNote((v) => !v)}
        title={showNote ? "Hide detail" : "Show detail"}
      >
        {bubbleCopy}
      </span>
      {showNote && (reason || companionMessage) && (
        <div
          className="bubble-note"
          style={{ WebkitAppRegion: "no-drag" } as React.CSSProperties}
          onClick={() => setShowNote(false)}
        >
          {reason && <p className="bubble-note-reason">{reason}</p>}
          {companionMessage && <p className="bubble-note-companion">{companionMessage}</p>}
        </div>
      )}
    </div>
  );
}
