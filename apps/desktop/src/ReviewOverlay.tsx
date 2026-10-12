import { useEffect, useState } from "react";
import { API_BASE } from "./api";
import type { ReviewEntry, SessionSnapshot } from "./types";

interface ReviewOverlayProps {
  session: SessionSnapshot;
  timeline: ReviewEntry[];
  mode: "timelapse" | "cinematic";
  onClose: () => void;
}

const SPEED_OPTIONS = [
  { label: "0.5x", value: 2 },
  { label: "1x", value: 1 },
  { label: "2x", value: 0.5 },
  { label: "4x", value: 0.25 },
];

export default function ReviewOverlay({ session, timeline, mode, onClose }: ReviewOverlayProps) {
  const [index, setIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(true);
  const [speedMultiplier, setSpeedMultiplier] = useState(1);
  const [imageError, setImageError] = useState(false);
  const frames = timeline.filter((entry) => !!entry.keyframe_path);

  const cinematicFrames = frames.filter((f, i) => {
    if (i === 0) return true;
    if (i === frames.length - 1) return true;
    if (f.label === "distracted" || f.label === "drifting") return true;
    return false;
  }).slice(0, 8);

  const activeFrames = mode === "cinematic" ? cinematicFrames : frames;
  const baseSpeed = mode === "cinematic" ? 2200 : 120;
  const effectiveSpeed = Math.round(baseSpeed * speedMultiplier);

  const displayLabel = (label: ReviewEntry["label"]) => {
    if (session.analysis_mode === "classification") {
      return label === "focused" ? "Focused" : "Unfocused";
    }
    return label.charAt(0).toUpperCase() + label.slice(1);
  };

  const displayNote = (frame: ReviewEntry) => {
    if (session.analysis_mode === "classification") {
      if (frame.label === "focused") {
        return "Staying on task.";
      }
      if (frame.label === "away") {
        return "You appear to be away from the task right now.";
      }
      if (frame.label === "distracted") {
        return "Attention is clearly off task. Reset to one thing.";
      }
      return "Attention is slipping. Bring your eyes back to the work.";
    }
    return frame.note;
  };

  useEffect(() => {
    setImageError(false);
  }, [index]);

  useEffect(() => {
    if (!isPlaying || activeFrames.length === 0) return;

    const timer = setTimeout(() => {
      setIndex((prev) => (prev + 1) % activeFrames.length);
      if (index === activeFrames.length - 1 && mode === "cinematic") {
        setIsPlaying(false);
      }
    }, effectiveSpeed);

    return () => clearTimeout(timer);
  }, [index, isPlaying, activeFrames, effectiveSpeed, mode]);

  if (activeFrames.length === 0) {
    return (
      <div className="review-overlay-backdrop" onClick={onClose}>
        <div className="review-overlay-content">
          <h2>No keyframes captured.</h2>
          <p style={{ opacity: 0.7, margin: "8px 0 16px" }}>
            Keyframes are saved when your focus label changes or a distraction is detected.
          </p>
          <button onClick={onClose}>Close</button>
        </div>
      </div>
    );
  }

  const currentFrame = activeFrames[index];
  const filename = currentFrame.keyframe_path?.split("/").pop();
  const src = `${API_BASE}/api/sessions/${encodeURIComponent(session.session_id)}/keyframes/${encodeURIComponent(filename ?? "")}`;

  const goToPrev = () => {
    setIndex((prev) => Math.max(0, prev - 1));
    setIsPlaying(false);
  };

  const goToNext = () => {
    setIndex((prev) => Math.min(activeFrames.length - 1, prev + 1));
    setIsPlaying(false);
  };

  return (
    <div className="review-overlay-backdrop">
      <div className={`review-overlay-content ${mode}-mode`}>
        <div className="overlay-header">
           <h2>{mode === "cinematic" ? "Cinematic Snippet" : "Session Time-lapse"}</h2>
           <button className="close-btn" onClick={onClose}>&times;</button>
        </div>

        <div className="overlay-stage">
           {imageError ? (
             <div className="overlay-frame-error">
               <span>Image could not be loaded</span>
             </div>
           ) : (
             <img
               src={src}
               key={src}
               alt={`Keyframe ${index + 1}`}
               className={`overlay-frame ${mode === "cinematic" ? "ken-burns" : ""}`}
               onError={() => setImageError(true)}
             />
           )}
           <div className="overlay-annotations">
              <span className={`label-badge label-${currentFrame.label}`}>{displayLabel(currentFrame.label)}</span>
              <p className="overlay-note">{displayNote(currentFrame)}</p>
              <p className="overlay-time">{new Date(currentFrame.timestamp).toLocaleTimeString()}</p>
           </div>
        </div>

        <div className="overlay-controls">
           <button onClick={goToPrev} disabled={index === 0}>Prev</button>
           <button onClick={() => setIsPlaying(!isPlaying)}>
              {isPlaying ? "Pause" : "Play"}
           </button>
           <button onClick={goToNext} disabled={index === activeFrames.length - 1}>Next</button>
           <div className="progress-bar">
              <div
                className="progress-fill"
                style={{ width: `${((index + 1) / activeFrames.length) * 100}%` }}
              />
           </div>
           <span>{index + 1} / {activeFrames.length}</span>
           <div className="speed-controls">
              {SPEED_OPTIONS.map((opt) => (
                <button
                  key={opt.label}
                  className={`speed-btn ${speedMultiplier === opt.value ? "selected" : ""}`}
                  onClick={() => setSpeedMultiplier(opt.value)}
                >
                  {opt.label}
                </button>
              ))}
           </div>
        </div>
      </div>
    </div>
  );
}
