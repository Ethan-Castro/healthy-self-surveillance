import { useEffect, useEffectEvent, useRef, useState } from "react";

import {
  createSession,
  fetchSession,
  fetchSetup,
  rescanSession,
  saveSession,
  submitReview,
  transitionSession,
} from "./api";
import type {
  FocusLabel,
  GemmaReviewStatus,
  RescanResult,
  ReviewInput,
  SessionConfig,
  SessionSnapshot,
  SetupStatus,
} from "./types";

const FAST_POLL_MS = 350;
const FOCUSED_REVIEW_MS = 2000;
const ACTIVE_REVIEW_MS = 1000;
const EARLY_REVIEW_MIN_MS = 700;

const DEFAULT_CONFIG: SessionConfig = {
  session_name: "Focus Buddy Session",
  include_screen_analysis: false,
  focused_review_cadence_ms: FOCUSED_REVIEW_MS,
  active_review_cadence_ms: ACTIVE_REVIEW_MS,
  temporary_review_window_sec: 600,
};

const LABEL_STYLES: Record<FocusLabel, string> = {
  focused: "label-focused",
  drifting: "label-drifting",
  distracted: "label-distracted",
  away: "label-away",
};

function captureStill(video: HTMLVideoElement | null, width: number): string | null {
  if (!video || video.readyState < 2 || video.videoWidth === 0 || video.videoHeight === 0) {
    return null;
  }

  const height = Math.max(1, Math.round((video.videoHeight / video.videoWidth) * width));
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;

  const context = canvas.getContext("2d");
  if (!context) {
    return null;
  }

  context.drawImage(video, 0, 0, width, height);
  return canvas.toDataURL("image/jpeg", 0.72);
}

function captureSignature(video: HTMLVideoElement | null): number[] | null {
  if (!video || video.readyState < 2 || video.videoWidth === 0 || video.videoHeight === 0) {
    return null;
  }

  const width = 12;
  const height = 8;
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;

  const context = canvas.getContext("2d");
  if (!context) {
    return null;
  }

  context.drawImage(video, 0, 0, width, height);
  const { data } = context.getImageData(0, 0, width, height);
  const signature: number[] = [];

  for (let index = 0; index < data.length; index += 4) {
    signature.push((data[index] + data[index + 1] + data[index + 2]) / 3);
  }

  return signature;
}

function signatureDelta(previous: number[] | null, next: number[] | null): number {
  if (!previous || !next || previous.length !== next.length) {
    return 1;
  }

  let total = 0;
  for (let index = 0; index < previous.length; index += 1) {
    total += Math.abs(previous[index] - next[index]);
  }
  return total / (previous.length * 255);
}

function formatTime(iso: string | null | undefined): string {
  if (!iso) {
    return "not yet";
  }
  return new Date(iso).toLocaleTimeString([], {
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatExpiry(iso: string | null | undefined): string | null {
  if (!iso) {
    return null;
  }
  return new Date(iso).toLocaleTimeString([], {
    hour: "numeric",
    minute: "2-digit",
  });
}

function labelCopy(label: FocusLabel): string {
  return label.charAt(0).toUpperCase() + label.slice(1);
}

function reviewStatusCopy(status: GemmaReviewStatus | null | undefined): {
  tone: "ok" | "warn" | "idle";
  label: string;
} {
  if (status === "reviewing") {
    return { tone: "warn", label: "Reviewing" };
  }
  if (status === "error") {
    return { tone: "warn", label: "Retrying soon" };
  }
  if (status === "ready") {
    return { tone: "ok", label: "Ready" };
  }
  return { tone: "idle", label: "Idle" };
}

function statusCopy(status: SessionSnapshot["status"] | null | undefined): string {
  if (!status) {
    return "Created";
  }
  return status.charAt(0).toUpperCase() + status.slice(1);
}

export default function App() {
  const [setup, setSetup] = useState<SetupStatus | null>(null);
  const [session, setSession] = useState<SessionSnapshot | null>(null);
  const [rescan, setRescan] = useState<RescanResult | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sessionName, setSessionName] = useState(DEFAULT_CONFIG.session_name);
  const [includeScreenAnalysis, setIncludeScreenAnalysis] = useState(false);
  const [cameraStream, setCameraStream] = useState<MediaStream | null>(null);
  const [screenStream, setScreenStream] = useState<MediaStream | null>(null);
  const cameraVideoRef = useRef<HTMLVideoElement | null>(null);
  const screenVideoRef = useRef<HTMLVideoElement | null>(null);
  const loopTimerRef = useRef<number | null>(null);
  const requestInFlightRef = useRef(false);
  const frameSequenceRef = useRef(0);
  const lastReviewSubmittedAtRef = useRef(0);
  const lastSignatureRef = useRef<number[] | null>(null);

  const setupCheck = useEffectEvent(async () => {
    try {
      const nextSetup = await fetchSetup();
      setSetup(nextSetup);
      setError(null);
    } catch (caught) {
      const nextError = caught instanceof Error ? caught.message : "Failed to check setup";
      setError(nextError);
    }
  });

  useEffect(() => {
    void setupCheck();
    const interval = window.setInterval(() => {
      void setupCheck();
    }, 4000);

    return () => window.clearInterval(interval);
  }, [setupCheck]);

  useEffect(() => {
    if (!cameraVideoRef.current) {
      return;
    }
    cameraVideoRef.current.srcObject = cameraStream;
  }, [cameraStream]);

  useEffect(() => {
    if (!screenVideoRef.current) {
      return;
    }
    screenVideoRef.current.srcObject = screenStream;
  }, [screenStream]);

  useEffect(() => {
    if (!includeScreenAnalysis && screenStream) {
      screenStream.getTracks().forEach((track) => track.stop());
      setScreenStream(null);
    }
  }, [includeScreenAnalysis, screenStream]);

  const syncLoop = useEffectEvent(async () => {
    if (!session) {
      return;
    }
    if (requestInFlightRef.current) {
      return;
    }

    requestInFlightRef.current = true;
    try {
      if (session.status === "running") {
        const now = Date.now();
        const active = session.current_label === "drifting" || session.current_label === "distracted";
        const cadence = active ? ACTIVE_REVIEW_MS : FOCUSED_REVIEW_MS;
        const currentSignature = captureSignature(cameraVideoRef.current);
        const delta = signatureDelta(lastSignatureRef.current, currentSignature);
        const shouldSubmit =
          !!cameraStream &&
          (lastReviewSubmittedAtRef.current === 0 ||
            now - lastReviewSubmittedAtRef.current >= cadence ||
            (delta >= 0.12 && now - lastReviewSubmittedAtRef.current >= EARLY_REVIEW_MIN_MS));

        if (shouldSubmit) {
          frameSequenceRef.current += 1;
          const reviewInput: ReviewInput = {
            frame_sequence: frameSequenceRef.current,
            camera_image_b64: captureStill(cameraVideoRef.current, 320),
            screen_image_b64:
              includeScreenAnalysis && screenStream ? captureStill(screenVideoRef.current, 240) : null,
            include_screen_analysis: includeScreenAnalysis,
            force_review: lastReviewSubmittedAtRef.current === 0,
          };
          const nextSnapshot = await submitReview(session.session_id, reviewInput);
          lastReviewSubmittedAtRef.current = now;
          lastSignatureRef.current = currentSignature;
          setSession(nextSnapshot);
          return;
        }
      }

      const nextSnapshot = await fetchSession(session.session_id);
      setSession(nextSnapshot);
    } catch (caught) {
      const nextError = caught instanceof Error ? caught.message : "Failed to sync session";
      setError(nextError);
    } finally {
      requestInFlightRef.current = false;
    }
  });

  useEffect(() => {
    if (!session) {
      return;
    }

    let cancelled = false;

    const schedule = () => {
      if (cancelled) {
        return;
      }
      loopTimerRef.current = window.setTimeout(() => {
        void run();
      }, FAST_POLL_MS);
    };

    const run = async () => {
      await syncLoop();
      schedule();
    };

    void run();

    return () => {
      cancelled = true;
      if (loopTimerRef.current !== null) {
        window.clearTimeout(loopTimerRef.current);
        loopTimerRef.current = null;
      }
      requestInFlightRef.current = false;
    };
  }, [session?.session_id, session?.status, syncLoop]);

  async function withBusy<T>(message: string, action: () => Promise<T>): Promise<T | undefined> {
    setBusy(message);
    setError(null);
    try {
      return await action();
    } catch (caught) {
      const nextError = caught instanceof Error ? caught.message : "Unexpected error";
      setError(nextError);
      return undefined;
    } finally {
      setBusy(null);
    }
  }

  async function enableCamera() {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: { width: 1280, height: 720 },
    });
    setCameraStream(stream);
  }

  function stopCamera() {
    cameraStream?.getTracks().forEach((track) => track.stop());
    setCameraStream(null);
  }

  async function enableScreen() {
    const stream = await navigator.mediaDevices.getDisplayMedia({
      audio: false,
      video: true,
    });
    setScreenStream(stream);
  }

  function stopScreen() {
    screenStream?.getTracks().forEach((track) => track.stop());
    setScreenStream(null);
  }

  async function startOrResumeSession() {
    if (!setup?.ready) {
      throw new Error(setup?.message ?? "Gemma 4 E2B is not ready yet");
    }
    if (!cameraStream) {
      throw new Error("Enable the camera before starting a session");
    }
    if (includeScreenAnalysis && !screenStream) {
      throw new Error("Enable screen capture or turn screen analysis off before starting");
    }

    setRescan(null);
    if (session?.status === "paused") {
      const resumed = await transitionSession(session.session_id, "start");
      setSession(resumed);
      return;
    }

    const created = await createSession({
      ...DEFAULT_CONFIG,
      session_name: sessionName.trim() || DEFAULT_CONFIG.session_name,
      include_screen_analysis: includeScreenAnalysis,
    });
    const started = await transitionSession(created.session_id, "start");
    frameSequenceRef.current = 0;
    lastReviewSubmittedAtRef.current = 0;
    lastSignatureRef.current = null;
    setSession(started);
  }

  async function pauseSession() {
    if (!session) {
      return;
    }
    const paused = await transitionSession(session.session_id, "pause");
    setSession(paused);
  }

  async function endSession() {
    if (!session) {
      return;
    }
    const stopped = await transitionSession(session.session_id, "stop");
    setSession(stopped);
    stopCamera();
    stopScreen();
  }

  const currentLabel = session?.current_label ?? "focused";
  const currentLabelClass = LABEL_STYLES[currentLabel];
  const temporaryExpiry = formatExpiry(session?.temporary_expires_at);
  const reviewChip = reviewStatusCopy(session?.review_status);
  const startBlocker =
    session?.status === "paused"
      ? null
      : !setup?.ready
        ? (setup?.message ?? "Gemma 4 E2B is not ready yet")
        : !cameraStream
          ? "Enable the camera to start the live buddy."
          : includeScreenAnalysis && !screenStream
            ? "Turn off screen analysis or enable screen capture to start."
            : null;
  const startDisabled =
    busy !== null ||
    session?.status === "running" ||
    startBlocker !== null;
  const pauseDisabled = busy !== null || session?.status !== "running";
  const endDisabled = busy !== null || !session || session.status === "stopped";
  const saveDisabled = busy !== null || !session || session.is_saved;
  const rescanDisabled = busy !== null || !session || !session.can_rescan;

  return (
    <main className="buddy-shell">
      <div className="buddy-backdrop buddy-backdrop-one" />
      <div className="buddy-backdrop buddy-backdrop-two" />

      <section className="buddy-card hero-card">
        <p className="eyebrow">Focus Buddy</p>
        <h1>Your local accountability companion.</h1>
        <p className="support-copy">
          One camera, one live check-in, one gentle nudge when your attention slips.
        </p>
      </section>

      <section className="buddy-card setup-card">
        <div className="section-header">
          <h2>Setup</h2>
          <span className={`status-chip ${setup?.ready ? "ok" : "warn"}`}>
            {setup?.ready ? "Gemma ready" : "Setup needed"}
          </span>
        </div>
        <p className="setup-message">
          {setup?.message ?? "Checking local Gemma setup..."}
        </p>
        <label className="field">
          <span>Session name</span>
          <input
            value={sessionName}
            onChange={(event) => setSessionName(event.target.value)}
            placeholder="Focus Buddy Session"
          />
        </label>
        <label className="toggle-row">
          <input
            type="checkbox"
            checked={includeScreenAnalysis}
            onChange={(event) => setIncludeScreenAnalysis(event.target.checked)}
            disabled={session?.status === "running" || session?.status === "paused"}
          />
          <span>Include screen analysis this session</span>
        </label>
        <div className="button-stack">
          <button onClick={() => void withBusy("Requesting camera", enableCamera)} disabled={!!cameraStream}>
            {cameraStream ? "Camera ready" : "Enable camera"}
          </button>
          {includeScreenAnalysis ? (
            <button onClick={() => void withBusy("Requesting screen", enableScreen)} disabled={!!screenStream}>
              {screenStream ? "Screen ready" : "Enable screen"}
            </button>
          ) : null}
        </div>
        {startBlocker ? <p className="inline-note">{startBlocker}</p> : <p className="inline-note">Ready to start a live session.</p>}
      </section>

      <section className="buddy-card companion-card">
        <div className="section-header">
          <h2>Buddy</h2>
          <span className={`status-chip ${reviewChip.tone}`}>
            {reviewChip.label}
          </span>
        </div>
        <div className="buddy-stage">
          <div className={`buddy-orb ${currentLabelClass}`}>
            <div className="buddy-eye left" />
            <div className="buddy-eye right" />
            <div className="buddy-mouth" />
          </div>
          <div className="buddy-copy">
            <p className="label-line">{labelCopy(currentLabel)}</p>
            <p className="reason-line">{session?.short_reason ?? "Waiting for the first review."}</p>
            <p className="message-line">
              {session?.companion_message ?? "I’ll stay gentle and keep you honest."}
            </p>
          </div>
        </div>
      </section>

      <section className="buddy-card camera-card">
        <div className="section-header">
          <h2>Camera</h2>
          <span className={`status-chip ${cameraStream ? "ok" : "idle"}`}>
            {cameraStream ? "Live" : "Off"}
          </span>
        </div>
        {cameraStream ? (
          <video ref={cameraVideoRef} autoPlay muted playsInline className="camera-preview" />
        ) : (
          <div className="camera-placeholder">Enable the camera to start a real focus session.</div>
        )}
        {includeScreenAnalysis ? (
          <div className="screen-row">
            <span className={`tiny-chip ${screenStream ? "ok" : "warn"}`}>
              {screenStream ? "Screen included" : "Screen not enabled"}
            </span>
          </div>
        ) : null}
        <video ref={screenVideoRef} autoPlay muted playsInline className="hidden-video" />
      </section>

      <section className="buddy-card controls-card">
        <div className="section-header">
          <h2>Session</h2>
          <span className={`status-chip status-${session?.status ?? "created"}`}>
            {statusCopy(session?.status)}
          </span>
        </div>
        <div className="button-grid">
          <button onClick={() => void withBusy("Starting session", startOrResumeSession)} disabled={startDisabled}>
            {session?.status === "paused" ? "Resume" : "Start"}
          </button>
          <button onClick={() => void withBusy("Pausing session", pauseSession)} disabled={pauseDisabled}>
            Pause
          </button>
          <button onClick={() => void withBusy("Ending session", endSession)} disabled={endDisabled}>
            End
          </button>
          <button
            onClick={() => void withBusy("Saving session", async () => {
              if (!session) {
                return;
              }
              const saved = await saveSession(session.session_id);
              setSession(saved);
            })}
            disabled={saveDisabled}
          >
            {session?.is_saved ? "Saved" : "Save session"}
          </button>
          <button
            onClick={() => void withBusy("Running rescan", async () => {
              if (!session) {
                return;
              }
              const nextRescan = await rescanSession(session.session_id);
              setRescan(nextRescan);
              const refreshed = await fetchSession(session.session_id);
              setSession(refreshed);
            })}
            disabled={rescanDisabled}
          >
            Rescan session
          </button>
        </div>
        <div className="meta-stack">
          <p>{busy ?? (startBlocker ?? "Ready when you are.")}</p>
          {session?.last_review_at ? <p>Last review: {formatTime(session.last_review_at)}</p> : null}
          {temporaryExpiry ? <p>Temporary keyframes expire at {temporaryExpiry} unless you save.</p> : null}
          {error ? <p className="error-text">{error}</p> : null}
        </div>
      </section>

      <section className="buddy-card log-card">
        <div className="section-header">
          <h2>Rolling log</h2>
          <span className="status-chip idle">{session?.summary.total_reviews ?? 0} reviews</span>
        </div>
        <div className="log-list">
          {session?.recent_reviews.length ? (
            session.recent_reviews
              .slice()
              .reverse()
              .map((review) => (
                <article key={`${review.mode}-${review.sequence}-${review.timestamp}`} className="log-item">
                  <div>
                    <strong>{labelCopy(review.label)}</strong>
                    <p>{review.note}</p>
                  </div>
                  <span>{formatTime(review.timestamp)}</span>
                </article>
              ))
          ) : (
            <div className="empty-state">Your rolling check-ins will appear here once the session starts.</div>
          )}
        </div>
      </section>

      <section className="buddy-card summary-card">
        <div className="section-header">
          <h2>Session glance</h2>
          <span className="status-chip idle">{Math.round((session?.summary.focus_ratio ?? 0) * 100)}% focused</span>
        </div>
        <div className="summary-grid">
          <article>
            <p>Total reviews</p>
            <strong>{session?.summary.total_reviews ?? 0}</strong>
          </article>
          <article>
            <p>Distraction checks</p>
            <strong>{session?.summary.distraction_reviews ?? 0}</strong>
          </article>
          <article>
            <p>Common reason</p>
            <strong>{session?.summary.most_common_reason ?? "none yet"}</strong>
          </article>
        </div>
        {rescan ? (
          <div className="rescan-block">
            <p className="rescan-title">Rescan summary</p>
            <p>
              Revised focus ratio: {Math.round(rescan.revised_summary.focus_ratio * 100)}% · timeline items:{" "}
              {rescan.revised_timeline.length}
            </p>
          </div>
        ) : null}
      </section>
    </main>
  );
}
