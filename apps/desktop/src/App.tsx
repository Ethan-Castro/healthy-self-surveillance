import { type ReactNode, useCallback, useEffect, useEffectEvent, useRef, useState } from "react";

import {
  clearMomentRemarkable,
  createSession,
  fetchAnalyticsInsights,
  fetchExperimentAnalytics,
  fetchPreferences,
  fetchSession,
  fetchSessionAnalytics,
  fetchSessionReview,
  fetchSessions,
  fetchSetup,
  fetchTodayAnalytics,
  fetchWeekAnalytics,
  markMomentRemarkable,
  markSessionRemarkable,
  rescanSession,
  saveSession,
  submitContext,
  submitReview,
  transitionSession,
  updatePreferences,
} from "./api";
import ReviewOverlay from "./ReviewOverlay";
import type {
  AnalysisMode,
  AnalyticsPreferences,
  ComparisonPoint,
  ConfidenceBucket,
  ContextCaptureReason,
  ContextCaptureRequest,
  DataSourceToggles,
  DayAnalyticsView,
  ExperimentComparisonView,
  FocusLabel,
  GemmaReviewStatus,
  InsightCard,
  LiveCoachingMode,
  ManualTags,
  RescanResult,
  RuntimeProfile,
  ReviewEntry,
  ReviewMode,
  ReviewInput,
  SessionAnalyticsDetail,
  SessionConfig,
  SessionReviewDetail,
  SessionSnapshot,
  SetupStatus,
  WeekAnalyticsView,
} from "./types";

const FAST_POLL_MS = 250;
const FOCUSED_REVIEW_MS = 1200;
const ACTIVE_REVIEW_MS = 650;
const EARLY_REVIEW_MIN_MS = 350;
const REVIEW_LIBRARY_POLL_MS = 5000;
const ANALYTICS_POLL_MS = 15000;
const CONTEXT_CAPTURE_INTERVAL_MS = 30000;
const DEBUG_PREFIX = "[Focus Buddy Debug]";

const DEFAULT_CAPTURE_TOGGLES: DataSourceToggles = {
  camera: true,
  screen: false,
  app_context: false,
  input_activity: false,
  sound_features: false,
  location: false,
  calendar_context: false,
  manual_tags: false,
};

const EMPTY_MANUAL_TAGS: ManualTags = {
  task: null,
  mood: null,
  energy: null,
  caffeine: null,
  environment: null,
  location_label: null,
  note: null,
  phone_present: null,
};

const DEFAULT_PREFERENCES: AnalyticsPreferences = {
  raw_retention_days: 7,
  keep_remarkable_raw: true,
  analytics_version: "v1",
  live_coaching_mode: "notifications",
  capture_toggles: DEFAULT_CAPTURE_TOGGLES,
  default_manual_tags: EMPTY_MANUAL_TAGS,
};

const DEFAULT_CONFIG: SessionConfig = {
  session_name: "Focus Buddy Session",
  include_screen_analysis: false,
  runtime_profile: "standard",
  analysis_mode: "annotation",
  live_coaching_mode: "notifications",
  capture_toggles: DEFAULT_CAPTURE_TOGGLES,
  manual_tags: EMPTY_MANUAL_TAGS,
  focused_review_cadence_ms: FOCUSED_REVIEW_MS,
  active_review_cadence_ms: ACTIVE_REVIEW_MS,
  timelapse_capture_interval_reviews: 1,
  temporary_review_window_sec: 600,
};

const LABEL_STYLES: Record<FocusLabel, string> = {
  focused: "label-focused",
  drifting: "label-drifting",
  distracted: "label-distracted",
  away: "label-away",
};

const FOCUS_LABELS: FocusLabel[] = ["focused", "drifting", "distracted", "away"];
const ORB_IMAGES_KEY = (label: FocusLabel) => `focus-buddy-orb-images-${label}`;

type OrbImagesMap = Record<FocusLabel, string[]>;
type DockTab = "live" | "analytics" | "review" | "patterns" | "settings";

type InputActivityCounts = {
  keyboard: number;
  mouse: number;
  scroll: number;
};

type SoundSnapshot = {
  rms: number | null;
  peak: number | null;
  bucket: string | null;
};

function loadOrbImages(label: FocusLabel): string[] {
  try {
    const raw = window.localStorage.getItem(ORB_IMAGES_KEY(label));
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw) as unknown;
    return Array.isArray(parsed) ? (parsed as string[]) : [];
  } catch {
    return [];
  }
}

function saveOrbImages(label: FocusLabel, images: string[]): void {
  window.localStorage.setItem(ORB_IMAGES_KEY(label), JSON.stringify(images));
}

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

function displayLabel(label: FocusLabel, analysisMode: AnalysisMode): string {
  if (analysisMode === "classification") {
    return label === "focused" ? "Focused" : "Unfocused";
  }
  return labelCopy(label);
}

function deterministicNote(label: FocusLabel): string {
  if (label === "focused") {
    return "Staying on task.";
  }
  if (label === "drifting") {
    return "Attention is slipping. Bring your eyes back to the work.";
  }
  if (label === "distracted") {
    return "Attention is clearly off task. Reset to one thing.";
  }
  return "You appear to be away from the task right now.";
}

function visibleNote(label: FocusLabel, note: string, analysisMode: AnalysisMode): string {
  if (analysisMode === "classification") {
    return deterministicNote(label);
  }
  return note;
}

function formatSessionStamp(iso: string): string {
  return new Date(iso).toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function reasonsCopy(reasons: string[]): string {
  if (!reasons.length) {
    return "No strong reason tag saved.";
  }
  return reasons.map((reason) => reason.replaceAll("_", " ")).join(" · ");
}

function keyframeSrc(sessionId: string | null | undefined, keyframePath: string | null | undefined): string | null {
  if (!sessionId || !keyframePath) {
    return null;
  }
  const filename = keyframePath.split("/").pop();
  if (!filename) {
    return null;
  }
  return `http://127.0.0.1:8000/api/sessions/${encodeURIComponent(sessionId)}/keyframes/${encodeURIComponent(filename)}`;
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

function formatDebugDetails(details: Record<string, unknown>): string {
  try {
    return JSON.stringify(details);
  } catch {
    return String(details);
  }
}

function debugLog(message: string, details?: Record<string, unknown>): void {
  const line = details ? `${message} ${formatDebugDetails(details)}` : message;
  console.log(`${DEBUG_PREFIX} ${line}`);
  if (window.desktopShell?.debugLog) {
    void window.desktopShell.debugLog(message, details);
  }
}

function statusCopy(status: SessionSnapshot["status"] | null | undefined): string {
  if (!status) {
    return "Created";
  }
  return status.charAt(0).toUpperCase() + status.slice(1);
}

function formatPercent(ratio: number | null | undefined): string {
  return `${Math.round((ratio ?? 0) * 100)}%`;
}

function formatDuration(ms: number | null | undefined): string {
  if (!ms || ms <= 0) {
    return "0m";
  }
  const totalSeconds = Math.round(ms / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }
  if (minutes > 0) {
    return `${minutes}m`;
  }
  return `${seconds}s`;
}

function formatHourLabel(hour: number): string {
  const date = new Date();
  date.setHours(hour, 0, 0, 0);
  return date.toLocaleTimeString([], {
    hour: "numeric",
  });
}

function prettifyKey(value: string | null | undefined): string {
  if (!value) {
    return "Unknown";
  }
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (match) => match.toUpperCase());
}

function confidenceCopy(bucket: ConfidenceBucket): string {
  return bucket.charAt(0).toUpperCase() + bucket.slice(1);
}

function liveCoachingCopy(mode: LiveCoachingMode): string {
  if (mode === "off") {
    return "Off";
  }
  if (mode === "notifications") {
    return "Notifications";
  }
  if (mode === "ambient") {
    return "Ambient";
  }
  return "Full companion";
}

function contextToggleCopy(key: keyof DataSourceToggles): string {
  return {
    camera: "Camera",
    screen: "Screen",
    app_context: "Frontmost app",
    input_activity: "Input activity",
    sound_features: "Sound features",
    location: "Location label",
    calendar_context: "Calendar context",
    manual_tags: "Manual tags",
  }[key];
}

function normalizeText(value: string | null | undefined): string | null {
  if (!value) {
    return null;
  }
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function sanitizeManualTags(tags: ManualTags): ManualTags {
  return {
    task: normalizeText(tags.task),
    mood: normalizeText(tags.mood),
    energy: normalizeText(tags.energy),
    caffeine: normalizeText(tags.caffeine),
    environment: normalizeText(tags.environment),
    location_label: normalizeText(tags.location_label),
    note: normalizeText(tags.note),
    phone_present: tags.phone_present ?? null,
  };
}

function mergeManualTags(base: ManualTags, incoming: ManualTags): ManualTags {
  return sanitizeManualTags({
    ...base,
    ...incoming,
  });
}

function isNudgeMessage(message: string | null | undefined): boolean {
  if (!message) {
    return false;
  }
  return message.startsWith("Quick reset:") || message.startsWith("Tiny reset:");
}

function FocusRibbon({ summary }: { summary: SessionSnapshot["summary"] }) {
  const total = summary.total_reviews || 1;
  return (
    <div className="focus-ribbon">
      {(Object.entries(summary.label_counts) as [FocusLabel, number][]).map(([label, count]) => (
        <div
          key={label}
          className={`ribbon-segment ${label}`}
          style={{ flexGrow: count / total }}
          title={`${labelCopy(label)}: ${count} reviews`}
        />
      ))}
    </div>
  );
}

function MetricTile({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail?: string | null;
}) {
  return (
    <article className="summary-grid analytics-summary-grid-item">
      <div className="analytics-metric-tile">
        <p>{label}</p>
        <strong>{value}</strong>
        {detail ? <span>{detail}</span> : null}
      </div>
    </article>
  );
}

function InsightList({
  insights,
  emptyCopy,
}: {
  insights: InsightCard[];
  emptyCopy: string;
}) {
  if (!insights.length) {
    return <div className="empty-state">{emptyCopy}</div>;
  }

  return (
    <div className="insight-list">
      {insights.map((insight) => (
        <article key={insight.id} className="insight-card">
          <div className="insight-header">
            <strong>{insight.title}</strong>
            <span className={`tiny-chip ${insight.confidence === "high" ? "ok" : "idle"}`}>
              {confidenceCopy(insight.confidence)}
            </span>
          </div>
          <p>{insight.summary}</p>
          <span className="insight-meta">
            {prettifyKey(insight.category)} · {insight.sample_size} samples
            {insight.date_range ? ` · ${insight.date_range}` : ""}
          </span>
        </article>
      ))}
    </div>
  );
}

function ComparisonList({
  points,
  emptyCopy,
}: {
  points: ComparisonPoint[];
  emptyCopy: string;
}) {
  if (!points.length) {
    return <div className="empty-state">{emptyCopy}</div>;
  }

  return (
    <div className="comparison-list">
      {points.map((point) => (
        <article key={`${point.dimension}:${point.key}`} className="comparison-card">
          <div className="comparison-topline">
            <strong>{prettifyKey(point.key)}</strong>
            <span>{formatPercent(point.avg_focus_ratio)}</span>
          </div>
          <p>
            {point.session_count} sessions · {point.sample_size} samples · {confidenceCopy(point.confidence)}
          </p>
          <p>
            Avg length {formatDuration(point.avg_session_length_ms)}
            {point.avg_recovery_ms ? ` · recovery ${formatDuration(point.avg_recovery_ms)}` : ""}
          </p>
        </article>
      ))}
    </div>
  );
}

function DockIcon({ tab }: { tab: DockTab }) {
  if (tab === "live") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M4 10.5 12 4l8 6.5V20a1 1 0 0 1-1 1h-4.5v-6h-5v6H5a1 1 0 0 1-1-1z" />
      </svg>
    );
  }

  if (tab === "analytics") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M5 19a1 1 0 0 1-1-1V6h2v11h14v2z" />
        <path d="M9 15.5 13 11l3 2.5 4-5 .001 3.4h1.999V5h-6.2v2h2.7l-2.7 3.4-3-2.5L7 13.7z" />
      </svg>
    );
  }

  if (tab === "review") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M5 4h14a1 1 0 0 1 1 1v11.5A1.5 1.5 0 0 1 18.5 18H8l-4 3V5a1 1 0 0 1 1-1z" />
        <path d="M8 9h8v2H8zm0 4h5v2H8z" />
      </svg>
    );
  }

  if (tab === "patterns") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="m12 3.6 2.1 4.3 4.7.7-3.4 3.3.8 4.7L12 14.3 7.8 16.6l.8-4.7-3.4-3.3 4.7-.7z" />
      </svg>
    );
  }

  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 8.5a3.5 3.5 0 1 1 0 7 3.5 3.5 0 0 1 0-7Zm8 3.5-.9-.4a7.8 7.8 0 0 0-.6-1.5l.5-.9a1 1 0 0 0-.2-1.2l-1.6-1.6a1 1 0 0 0-1.2-.2l-.9.5a7.8 7.8 0 0 0-1.5-.6L13 4a1 1 0 0 0-1-.8h-2a1 1 0 0 0-1 .8l-.4.9a7.8 7.8 0 0 0-1.5.6l-.9-.5a1 1 0 0 0-1.2.2L3.4 6.8a1 1 0 0 0-.2 1.2l.5.9a7.8 7.8 0 0 0-.6 1.5L2.2 12a1 1 0 0 0 0 1l.9.4a7.8 7.8 0 0 0 .6 1.5l-.5.9a1 1 0 0 0 .2 1.2l1.6 1.6a1 1 0 0 0 1.2.2l.9-.5a7.8 7.8 0 0 0 1.5.6l.4.9a1 1 0 0 0 1 .8h2a1 1 0 0 0 1-.8l.4-.9a7.8 7.8 0 0 0 1.5-.6l.9.5a1 1 0 0 0 1.2-.2l1.6-1.6a1 1 0 0 0 .2-1.2l-.5-.9a7.8 7.8 0 0 0 .6-1.5l.9-.4a1 1 0 0 0 .8-1v-2a1 1 0 0 0-.8-1Z" />
    </svg>
  );
}

function dockTabCopy(tab: DockTab): string {
  return {
    live: "Live",
    analytics: "Stats",
    review: "Review",
    patterns: "Patterns",
    settings: "Settings",
  }[tab];
}

function SectionHero({
  eyebrow,
  title,
  copy,
}: {
  eyebrow: string;
  title: string;
  copy: string;
}) {
  return (
    <section className="buddy-card section-hero-card">
      <p className="eyebrow section-eyebrow">{eyebrow}</p>
      <h2>{title}</h2>
      <p className="section-copy">{copy}</p>
    </section>
  );
}

function DisclosureCard({
  title,
  badge,
  storageKey,
  defaultOpen = false,
  className = "",
  children,
}: {
  title: string;
  badge?: ReactNode;
  storageKey: string;
  defaultOpen?: boolean;
  className?: string;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(() => {
    const saved = window.localStorage.getItem(storageKey);
    if (saved === "open") {
      return true;
    }
    if (saved === "closed") {
      return false;
    }
    return defaultOpen;
  });

  useEffect(() => {
    window.localStorage.setItem(storageKey, open ? "open" : "closed");
  }, [open, storageKey]);

  return (
    <section className={`buddy-card dropdown-card ${className}`.trim()}>
      <button
        type="button"
        className={`dropdown-trigger ${open ? "open" : ""}`}
        onClick={() => setOpen((current) => !current)}
        aria-expanded={open}
      >
        <div className="dropdown-title-group">
          <h2>{title}</h2>
        </div>
        <div className="dropdown-meta">
          {badge}
          <span className="dropdown-chevron" aria-hidden="true">
            {open ? "Hide" : "Show"}
          </span>
        </div>
      </button>
      {open ? <div className="dropdown-content">{children}</div> : null}
    </section>
  );
}

export default function App() {
  const [setup, setSetup] = useState<SetupStatus | null>(null);
  const [preferences, setPreferences] = useState<AnalyticsPreferences | null>(null);
  const [session, setSession] = useState<SessionSnapshot | null>(null);
  const [sessions, setSessions] = useState<SessionSnapshot[]>([]);
  const [rescan, setRescan] = useState<RescanResult | null>(null);
  const [reviewDetail, setReviewDetail] = useState<SessionReviewDetail | null>(null);
  const [sessionAnalytics, setSessionAnalytics] = useState<SessionAnalyticsDetail | null>(null);
  const [todayAnalytics, setTodayAnalytics] = useState<DayAnalyticsView | null>(null);
  const [weekAnalytics, setWeekAnalytics] = useState<WeekAnalyticsView | null>(null);
  const [experimentAnalytics, setExperimentAnalytics] = useState<ExperimentComparisonView | null>(null);
  const [globalInsights, setGlobalInsights] = useState<InsightCard[]>([]);
  const [reviewSessionId, setReviewSessionId] = useState<string | null>(null);
  const [reviewTimelineMode, setReviewTimelineMode] = useState<ReviewMode>("live");
  const [overlayMode, setOverlayMode] = useState<"timelapse" | "cinematic" | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sessionName, setSessionName] = useState(DEFAULT_CONFIG.session_name);
  const [includeScreenAnalysis, setIncludeScreenAnalysis] = useState(false);
  const [analysisMode, setAnalysisMode] = useState<AnalysisMode>(() => {
    const saved = window.localStorage.getItem("focus-buddy-analysis-mode");
    return saved === "classification" ? "classification" : "annotation";
  });
  const [runtimeProfile, setRuntimeProfile] = useState<RuntimeProfile>(() => {
    const saved = window.localStorage.getItem("focus-buddy-runtime-profile");
    if (saved === "higher_accuracy" || saved === "edge") return saved;
    return "standard";
  });
  const [liveCoachingMode, setLiveCoachingMode] = useState<LiveCoachingMode>(
    DEFAULT_CONFIG.live_coaching_mode,
  );
  const [captureToggles, setCaptureToggles] = useState<DataSourceToggles>(DEFAULT_CAPTURE_TOGGLES);
  const [manualTags, setManualTags] = useState<ManualTags>(EMPTY_MANUAL_TAGS);
  const [retentionDays, setRetentionDays] = useState(DEFAULT_PREFERENCES.raw_retention_days);
  const [keepRemarkableRaw, setKeepRemarkableRaw] = useState(
    DEFAULT_PREFERENCES.keep_remarkable_raw,
  );
  const [showBubble, setShowBubble] = useState(
    () => window.localStorage.getItem("focus-buddy-show-orb") !== "off",
  );
  const [desktopNudges, setDesktopNudges] = useState(
    () => window.localStorage.getItem("focus-buddy-desktop-nudges") !== "off",
  );
  const [orbImages, setOrbImages] = useState<OrbImagesMap>(() => ({
    focused: loadOrbImages("focused"),
    drifting: loadOrbImages("drifting"),
    distracted: loadOrbImages("distracted"),
    away: loadOrbImages("away"),
  }));
  const [soundMonitorEnabled, setSoundMonitorEnabled] = useState(false);
  const [activeDockTab, setActiveDockTab] = useState<DockTab>(() => {
    const saved = window.localStorage.getItem("focus-buddy-active-tab");
    if (
      saved === "live" ||
      saved === "analytics" ||
      saved === "review" ||
      saved === "patterns" ||
      saved === "settings"
    ) {
      return saved;
    }
    return "live";
  });

  const preferencesLoadedRef = useRef(false);
  const orbCycleIndexRef = useRef<Record<FocusLabel, number>>({
    focused: 0,
    drifting: 0,
    distracted: 0,
    away: 0,
  });
  const cameraVideoRef = useRef<HTMLVideoElement | null>(null);
  const screenVideoRef = useRef<HTMLVideoElement | null>(null);
  const cameraStreamRef = useRef<MediaStream | null>(null);
  const screenStreamRef = useRef<MediaStream | null>(null);
  const microphoneStreamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const soundAnalyserRef = useRef<AnalyserNode | null>(null);
  const soundBufferRef = useRef<Uint8Array | null>(null);
  const loopTimerRef = useRef<number | null>(null);
  const requestInFlightRef = useRef(false);
  const frameSequenceRef = useRef(0);
  const lastReviewSubmittedAtRef = useRef(0);
  const lastSignatureRef = useRef<number[] | null>(null);
  const lastDesktopNotificationKeyRef = useRef<string | null>(null);
  const previousVisibleLabelRef = useRef<FocusLabel | null>(null);
  const lastNudgeContextKeyRef = useRef<string | null>(null);
  const liveSectionRef = useRef<HTMLDivElement | null>(null);
  const analyticsSectionRef = useRef<HTMLDivElement | null>(null);
  const reviewSectionRef = useRef<HTMLDivElement | null>(null);
  const patternsSectionRef = useRef<HTMLDivElement | null>(null);
  const settingsSectionRef = useRef<HTMLDivElement | null>(null);
  const inputActivityRef = useRef<InputActivityCounts>({
    keyboard: 0,
    mouse: 0,
    scroll: 0,
  });
  const lastMouseEventAtRef = useRef(0);

  const [cameraStream, setCameraStream] = useState<MediaStream | null>(null);
  const [screenStream, setScreenStream] = useState<MediaStream | null>(null);

  useEffect(() => {
    cameraStreamRef.current = cameraStream;
  }, [cameraStream]);

  useEffect(() => {
    screenStreamRef.current = screenStream;
  }, [screenStream]);

  useEffect(() => {
    window.localStorage.setItem("focus-buddy-analysis-mode", analysisMode);
  }, [analysisMode]);

  useEffect(() => {
    window.localStorage.setItem("focus-buddy-runtime-profile", runtimeProfile);
  }, [runtimeProfile]);

  useEffect(() => {
    window.localStorage.setItem("focus-buddy-show-orb", showBubble ? "on" : "off");
    debugLog("renderer orb preference changed", { enabled: showBubble });
    if (window.desktopShell?.toggleBubble) {
      void window.desktopShell.toggleBubble(showBubble);
    }
  }, [showBubble]);

  useEffect(() => {
    window.localStorage.setItem("focus-buddy-desktop-nudges", desktopNudges ? "on" : "off");
    debugLog("renderer desktop nudges changed", { enabled: desktopNudges });
  }, [desktopNudges]);

  useEffect(() => {
    window.localStorage.setItem("focus-buddy-active-tab", activeDockTab);
  }, [activeDockTab]);

  const refreshPreferences = useEffectEvent(async () => {
    try {
      const nextPreferences = await fetchPreferences();
      setPreferences(nextPreferences);
      if (!preferencesLoadedRef.current) {
        preferencesLoadedRef.current = true;
        setLiveCoachingMode(nextPreferences.live_coaching_mode);
        setCaptureToggles({
          ...DEFAULT_CAPTURE_TOGGLES,
          ...nextPreferences.capture_toggles,
          camera: true,
          screen: false,
        });
        setManualTags(mergeManualTags(EMPTY_MANUAL_TAGS, nextPreferences.default_manual_tags));
        setRetentionDays(nextPreferences.raw_retention_days);
        setKeepRemarkableRaw(nextPreferences.keep_remarkable_raw);
      }
      setError(null);
    } catch (caught) {
      const nextError = caught instanceof Error ? caught.message : "Failed to load analytics settings";
      setError(nextError);
    }
  });

  const refreshSetup = useEffectEvent(async () => {
    try {
      const nextSetup = await fetchSetup();
      setSetup(nextSetup);
      setError(null);
    } catch (caught) {
      const nextError = caught instanceof Error ? caught.message : "Failed to check setup";
      setError(nextError);
    }
  });

  const refreshSelectedReview = useEffectEvent(async (selectedSessionId: string | null) => {
    if (!selectedSessionId) {
      setReviewDetail(null);
      setSessionAnalytics(null);
      return;
    }

    try {
      const [detail, analytics] = await Promise.all([
        fetchSessionReview(selectedSessionId),
        fetchSessionAnalytics(selectedSessionId),
      ]);
      setReviewDetail(detail);
      setSessionAnalytics(analytics);
      setError(null);
      if (reviewTimelineMode === "rescan" && detail.rescan_timeline.length === 0) {
        setReviewTimelineMode("live");
      }
    } catch (caught) {
      const nextError = caught instanceof Error ? caught.message : "Failed to load selected session";
      setError(nextError);
    }
  });

  const refreshAnalyticsViews = useEffectEvent(async () => {
    try {
      const [today, week, experiments, insights] = await Promise.all([
        fetchTodayAnalytics(),
        fetchWeekAnalytics(),
        fetchExperimentAnalytics(),
        fetchAnalyticsInsights(),
      ]);
      setTodayAnalytics(today);
      setWeekAnalytics(week);
      setExperimentAnalytics(experiments);
      setGlobalInsights(insights);
      setError(null);
    } catch (caught) {
      const nextError = caught instanceof Error ? caught.message : "Failed to load analytics views";
      setError(nextError);
    }
  });

  const refreshSessionLibrary = useEffectEvent(async (preferredSessionId?: string | null) => {
    try {
      const nextSessions = (await fetchSessions()).filter(
        (candidate) => candidate.summary.total_reviews > 0,
      );
      setSessions(nextSessions);
      setError(null);

      const requestedId = preferredSessionId ?? reviewSessionId ?? session?.session_id ?? null;
      const nextSelectedId =
        requestedId ??
        nextSessions[0]?.session_id ??
        null;

      setReviewSessionId(nextSelectedId);
    } catch (caught) {
      const nextError = caught instanceof Error ? caught.message : "Failed to refresh saved sessions";
      setError(nextError);
    }
  });

  useEffect(() => {
    void refreshPreferences();
    void refreshSetup();
    void refreshSessionLibrary();
    void refreshAnalyticsViews();

    const setupInterval = window.setInterval(() => {
      void refreshSetup();
    }, 4000);
    const libraryInterval = window.setInterval(() => {
      void refreshSessionLibrary();
    }, REVIEW_LIBRARY_POLL_MS);
    const analyticsInterval = window.setInterval(() => {
      void refreshAnalyticsViews();
    }, ANALYTICS_POLL_MS);

    return () => {
      window.clearInterval(setupInterval);
      window.clearInterval(libraryInterval);
      window.clearInterval(analyticsInterval);
    };
  }, []);

  useEffect(() => {
    void refreshSelectedReview(reviewSessionId);
  }, [reviewSessionId]);

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

  useEffect(() => {
    if (captureToggles.sound_features) {
      return;
    }
    microphoneStreamRef.current?.getTracks().forEach((track) => track.stop());
    microphoneStreamRef.current = null;
    soundAnalyserRef.current = null;
    soundBufferRef.current = null;
    if (audioContextRef.current) {
      void audioContextRef.current.close();
      audioContextRef.current = null;
    }
    setSoundMonitorEnabled(false);
  }, [captureToggles.sound_features]);

  useEffect(() => {
    const onKeyDown = () => {
      inputActivityRef.current.keyboard += 1;
    };
    const onMouseMove = () => {
      const now = Date.now();
      if (now - lastMouseEventAtRef.current < 200) {
        return;
      }
      lastMouseEventAtRef.current = now;
      inputActivityRef.current.mouse += 1;
    };
    const onWheel = () => {
      inputActivityRef.current.scroll += 1;
    };

    window.addEventListener("keydown", onKeyDown, true);
    window.addEventListener("mousemove", onMouseMove, true);
    window.addEventListener("wheel", onWheel, true);
    return () => {
      window.removeEventListener("keydown", onKeyDown, true);
      window.removeEventListener("mousemove", onMouseMove, true);
      window.removeEventListener("wheel", onWheel, true);
    };
  }, []);

  async function ensureSoundMonitor(): Promise<void> {
    if (soundAnalyserRef.current && soundBufferRef.current) {
      return;
    }

    const stream = await navigator.mediaDevices.getUserMedia({
      audio: true,
      video: false,
    });
    const AudioContextCtor =
      window.AudioContext ??
      (window as Window & typeof globalThis & { webkitAudioContext?: typeof AudioContext })
        .webkitAudioContext;

    if (!AudioContextCtor) {
      stream.getTracks().forEach((track) => track.stop());
      throw new Error("This browser does not support local audio analysis");
    }

    const audioContext = new AudioContextCtor();
    const analyser = audioContext.createAnalyser();
    analyser.fftSize = 256;
    analyser.smoothingTimeConstant = 0.6;
    const source = audioContext.createMediaStreamSource(stream);
    source.connect(analyser);

    microphoneStreamRef.current = stream;
    audioContextRef.current = audioContext;
    soundAnalyserRef.current = analyser;
    soundBufferRef.current = new Uint8Array(new ArrayBuffer(analyser.fftSize));
    setSoundMonitorEnabled(true);
    debugLog("sound monitor enabled");
  }

  function readSoundSnapshot(): SoundSnapshot {
    const analyser = soundAnalyserRef.current;
    const buffer = soundBufferRef.current;
    if (!analyser || !buffer) {
      return { rms: null, peak: null, bucket: null };
    }

    const analysisBuffer = buffer as Uint8Array<ArrayBuffer>;
    analyser.getByteTimeDomainData(analysisBuffer);
    let sumSquares = 0;
    let peak = 0;
    for (const sample of analysisBuffer) {
      const normalized = (sample - 128) / 128;
      const amplitude = Math.abs(normalized);
      sumSquares += normalized * normalized;
      if (amplitude > peak) {
        peak = amplitude;
      }
    }

    const rms = Math.sqrt(sumSquares / buffer.length);
    let bucket = "quiet";
    if (peak >= 0.32 || rms >= 0.18) {
      bucket = "loud";
    } else if (peak >= 0.18 || rms >= 0.08) {
      bucket = "medium";
    }

    return {
      rms: Number(rms.toFixed(4)),
      peak: Number(peak.toFixed(4)),
      bucket,
    };
  }

  const captureContextNow = useEffectEvent(async (reason: ContextCaptureReason) => {
    if (!session) {
      return;
    }

    const toggles = session.capture_toggles;
    const shouldCapture =
      toggles.app_context ||
      toggles.input_activity ||
      toggles.sound_features ||
      toggles.location ||
      toggles.calendar_context ||
      toggles.manual_tags ||
      toggles.screen;

    if (!shouldCapture) {
      return;
    }

    let desktopContext:
      | {
          appName?: string | null;
          windowTitle?: string | null;
          calendarTitle?: string | null;
          calendarCategory?: string | null;
          systemIdleSeconds?: number | null;
          systemIdleState?: string | null;
        }
      | null = null;

    if ((toggles.app_context || toggles.calendar_context || toggles.input_activity) && window.desktopShell?.getDesktopContext) {
      try {
        desktopContext = await window.desktopShell.getDesktopContext();
      } catch (caught) {
        debugLog("desktop context request failed", {
          error: caught instanceof Error ? caught.message : "unknown",
        });
      }
    }

    let sound = { rms: null, peak: null, bucket: null } as SoundSnapshot;
    if (toggles.sound_features) {
      try {
        await ensureSoundMonitor();
        sound = readSoundSnapshot();
      } catch (caught) {
        debugLog("sound monitor capture failed", {
          error: caught instanceof Error ? caught.message : "unknown",
        });
      }
    }

    const manualTagsToSend = sanitizeManualTags(
      toggles.manual_tags || toggles.location ? manualTags : EMPTY_MANUAL_TAGS,
    );
    const keyboardEvents = toggles.input_activity ? inputActivityRef.current.keyboard : 0;
    const mouseEvents = toggles.input_activity ? inputActivityRef.current.mouse : 0;
    const scrollEvents = toggles.input_activity ? inputActivityRef.current.scroll : 0;
    if (toggles.input_activity) {
      inputActivityRef.current = { keyboard: 0, mouse: 0, scroll: 0 };
    }

    const payload: ContextCaptureRequest = {
      reason,
      device_id: "mac",
      capture_source: includeScreenAnalysis && !!screenStreamRef.current ? "mac_screen" : "mac_camera",
      context_source: "mac",
      screen_enabled: includeScreenAnalysis && !!screenStreamRef.current,
      app_name: toggles.app_context ? desktopContext?.appName ?? null : null,
      window_title: toggles.app_context ? desktopContext?.windowTitle ?? null : null,
      system_idle_seconds:
        toggles.input_activity || toggles.app_context ? desktopContext?.systemIdleSeconds ?? null : null,
      system_idle_state:
        toggles.input_activity || toggles.app_context ? desktopContext?.systemIdleState ?? null : null,
      keyboard_events: keyboardEvents,
      mouse_events: mouseEvents,
      scroll_events: scrollEvents,
      sound_rms: toggles.sound_features ? sound.rms : null,
      sound_peak: toggles.sound_features ? sound.peak : null,
      sound_bucket: toggles.sound_features ? sound.bucket : null,
      location_label: toggles.location ? normalizeText(manualTags.location_label) : null,
      calendar_title: toggles.calendar_context ? desktopContext?.calendarTitle ?? null : null,
      calendar_category: toggles.calendar_context ? desktopContext?.calendarCategory ?? null : null,
      manual_tags: manualTagsToSend,
      phone_present: toggles.manual_tags ? manualTags.phone_present ?? null : null,
    };

    try {
      const nextSnapshot = await submitContext(session.session_id, payload);
      setSession(nextSnapshot);
      if (reviewSessionId === session.session_id) {
        void refreshSelectedReview(session.session_id);
      }
      debugLog("renderer context submitted", {
        sessionId: session.session_id,
        reason,
        appName: payload.app_name,
        locationLabel: payload.location_label,
        soundBucket: payload.sound_bucket,
      });
    } catch (caught) {
      debugLog("renderer context submit failed", {
        sessionId: session.session_id,
        reason,
        error: caught instanceof Error ? caught.message : "unknown",
      });
    }
  });

  useEffect(() => {
    if (!session || session.status !== "running") {
      previousVisibleLabelRef.current = session?.current_label ?? null;
      lastNudgeContextKeyRef.current = null;
      return;
    }

    void captureContextNow("start");
    const interval = window.setInterval(() => {
      void captureContextNow("interval");
    }, CONTEXT_CAPTURE_INTERVAL_MS);

    return () => {
      window.clearInterval(interval);
    };
  }, [session?.session_id, session?.status]);

  useEffect(() => {
    if (!session || session.status !== "running" || !session.last_review_at) {
      previousVisibleLabelRef.current = session?.current_label ?? null;
      return;
    }

    const previous = previousVisibleLabelRef.current;
    if (previous && previous !== session.current_label) {
      void captureContextNow("transition");
    }
    previousVisibleLabelRef.current = session.current_label;
  }, [session?.current_label, session?.last_review_at, session?.session_id, session?.status]);

  useEffect(() => {
    if (!session || session.status !== "running" || !session.last_review_at) {
      lastNudgeContextKeyRef.current = null;
      return;
    }
    if (!isNudgeMessage(session.companion_message)) {
      return;
    }

    const key = `${session.session_id}:${session.last_review_at}:${session.companion_message}`;
    if (lastNudgeContextKeyRef.current === key) {
      return;
    }
    lastNudgeContextKeyRef.current = key;
    void captureContextNow("nudge");
  }, [session?.companion_message, session?.last_review_at, session?.session_id, session?.status]);

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
          !!cameraStreamRef.current &&
          (lastReviewSubmittedAtRef.current === 0 ||
            now - lastReviewSubmittedAtRef.current >= cadence ||
            (delta >= 0.12 && now - lastReviewSubmittedAtRef.current >= EARLY_REVIEW_MIN_MS));

        if (shouldSubmit) {
          frameSequenceRef.current += 1;
          const reviewInput: ReviewInput = {
            frame_sequence: frameSequenceRef.current,
            camera_image_b64: captureStill(cameraVideoRef.current, 320),
            screen_image_b64:
              includeScreenAnalysis && screenStreamRef.current ? captureStill(screenVideoRef.current, 240) : null,
            include_screen_analysis: includeScreenAnalysis,
            force_review: lastReviewSubmittedAtRef.current === 0,
          };
          debugLog("renderer submitting live review", {
            sessionId: session.session_id,
            frameSequence: reviewInput.frame_sequence,
            forceReview: reviewInput.force_review,
            includeScreenAnalysis,
            cadenceMs: cadence,
            delta: Number(delta.toFixed(3)),
          });
          const nextSnapshot = await submitReview(session.session_id, reviewInput);
          lastReviewSubmittedAtRef.current = now;
          lastSignatureRef.current = currentSignature;
          setSession(nextSnapshot);
          setError(null);
          if (reviewSessionId === nextSnapshot.session_id) {
            void refreshSelectedReview(nextSnapshot.session_id);
          }
          void refreshAnalyticsViews();
          debugLog("renderer live review accepted", {
            sessionId: nextSnapshot.session_id,
            reviewStatus: nextSnapshot.review_status,
            currentLabel: nextSnapshot.current_label,
            lastReviewAt: nextSnapshot.last_review_at,
          });
          return;
        }
      }

      const nextSnapshot = await fetchSession(session.session_id);
      setSession(nextSnapshot);
      setError(null);
    } catch (caught) {
      const nextError = caught instanceof Error ? caught.message : "Failed to sync session";
      setError(nextError);
      debugLog("renderer session sync failed", {
        sessionId: session.session_id,
        error: nextError,
      });
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
  }, [session?.session_id, session?.status]);

  useEffect(() => {
    if (!desktopNudges || !session || session.status !== "running" || !session.last_review_at) {
      return;
    }

    const currentMode = session.analysis_mode ?? analysisMode;
    const visibleReason = visibleNote(session.current_label, session.short_reason, currentMode);
    const shouldNotify =
      liveCoachingMode !== "off" &&
      (session.current_label === "away" ||
        session.current_label === "distracted" ||
        isNudgeMessage(session.companion_message));

    if (!shouldNotify) {
      return;
    }

    const notificationKey = [
      session.session_id,
      session.last_review_at,
      session.current_label,
      session.companion_message,
    ].join(":");

    if (lastDesktopNotificationKeyRef.current === notificationKey) {
      return;
    }
    lastDesktopNotificationKeyRef.current = notificationKey;

    if (window.desktopShell?.notify) {
      const payload = {
        title: `Focus Buddy: ${displayLabel(session.current_label, currentMode)}`,
        body: `${visibleReason} ${session.companion_message}`.trim(),
        silent: false,
      };
      debugLog("renderer sending desktop notification", {
        sessionId: session.session_id,
        label: session.current_label,
        title: payload.title,
        body: payload.body,
      });
      void window.desktopShell
        .notify(payload)
        .then((result) => {
          debugLog("renderer desktop notification result", {
            sessionId: session.session_id,
            ok: result.ok,
          });
        })
        .catch((caught) => {
          const message = caught instanceof Error ? caught.message : "unknown error";
          debugLog("renderer desktop notification failed", {
            sessionId: session.session_id,
            error: message,
          });
        });
    } else {
      debugLog("renderer desktop notification unavailable", {
        sessionId: session.session_id,
      });
    }
  }, [
    analysisMode,
    desktopNudges,
    liveCoachingMode,
    session?.analysis_mode,
    session?.companion_message,
    session?.current_label,
    session?.last_review_at,
    session?.session_id,
    session?.short_reason,
    session?.status,
  ]);

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

  const handleOrbImageUpload = useCallback((label: FocusLabel, files: FileList | null) => {
    if (!files || files.length === 0) {
      return;
    }
    const readers = Array.from(files).map(
      (file) =>
        new Promise<string>((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(reader.result as string);
          reader.onerror = reject;
          reader.readAsDataURL(file);
        }),
    );
    void Promise.all(readers).then((newDataUrls) => {
      setOrbImages((prev) => {
        const next = [...prev[label], ...newDataUrls];
        saveOrbImages(label, next);
        return { ...prev, [label]: next };
      });
    });
  }, []);

  const handleOrbImageRemove = useCallback((label: FocusLabel, index: number) => {
    setOrbImages((prev) => {
      const next = prev[label].filter((_, currentIndex) => currentIndex !== index);
      saveOrbImages(label, next);
      orbCycleIndexRef.current[label] = 0;
      return { ...prev, [label]: next };
    });
  }, []);

  async function enableCamera() {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: { width: 1280, height: 720 },
    });
    setCameraStream(stream);
  }

  function stopCamera() {
    cameraStreamRef.current?.getTracks().forEach((track) => track.stop());
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
    screenStreamRef.current?.getTracks().forEach((track) => track.stop());
    setScreenStream(null);
  }

  function buildSessionConfig(): SessionConfig {
    const nextManualTags = sanitizeManualTags({
      ...manualTags,
      phone_present: manualTags.phone_present ?? null,
    });
    const nextCaptureToggles: DataSourceToggles = {
      ...captureToggles,
      camera: true,
      screen: includeScreenAnalysis,
    };

    return {
      ...DEFAULT_CONFIG,
      session_name: sessionName.trim() || DEFAULT_CONFIG.session_name,
      include_screen_analysis: includeScreenAnalysis,
      runtime_profile: runtimeProfile,
      analysis_mode: analysisMode,
      live_coaching_mode: liveCoachingMode,
      capture_toggles: nextCaptureToggles,
      manual_tags: nextManualTags,
    };
  }

  async function startOrResumeSession() {
    if (!setup?.ready) {
      throw new Error(setup?.message ?? "Model is not ready yet");
    }
    if (!cameraStreamRef.current) {
      throw new Error("Enable the camera before starting a session");
    }
    if (includeScreenAnalysis && !screenStreamRef.current) {
      throw new Error("Enable screen capture or turn screen analysis off before starting");
    }

    if (captureToggles.sound_features) {
      try {
        await ensureSoundMonitor();
      } catch (caught) {
        debugLog("sound monitor enable failed before session start", {
          error: caught instanceof Error ? caught.message : "unknown",
        });
      }
    }

    setRescan(null);
    if (session?.status === "paused") {
      const resumed = await transitionSession(session.session_id, "start");
      setSession(resumed);
      await refreshSessionLibrary(resumed.session_id);
      await refreshAnalyticsViews();
      return;
    }

    const created = await createSession(buildSessionConfig());
    const started = await transitionSession(created.session_id, "start");
    frameSequenceRef.current = 0;
    lastReviewSubmittedAtRef.current = 0;
    lastSignatureRef.current = null;
    setSession(started);
    setReviewSessionId(started.session_id);
    await refreshSessionLibrary(started.session_id);
    await refreshAnalyticsViews();
  }

  async function pauseSession() {
    if (!session) {
      return;
    }
    const paused = await transitionSession(session.session_id, "pause");
    setSession(paused);
    await refreshSessionLibrary(paused.session_id);
  }

  async function endSession() {
    if (!session) {
      return;
    }
    void captureContextNow("stop");
    const stopped = await transitionSession(session.session_id, "stop");
    setSession(stopped);
    stopCamera();
    stopScreen();
    await refreshSessionLibrary(stopped.session_id);
    await refreshAnalyticsViews();
  }

  async function saveCurrentSession() {
    if (!session) {
      return;
    }
    const saved = await saveSession(session.session_id);
    setSession(saved);
    await refreshSessionLibrary(saved.session_id);
    await refreshAnalyticsViews();
  }

  async function runRescan() {
    if (!session) {
      return;
    }
    const nextRescan = await rescanSession(session.session_id);
    setRescan(nextRescan);
    const refreshed = await fetchSession(session.session_id);
    setSession(refreshed);
    setReviewTimelineMode("rescan");
    await refreshSessionLibrary(session.session_id);
    await refreshAnalyticsViews();
  }

  async function saveAnalyticsSettings() {
    const nextPreferences = await updatePreferences({
      raw_retention_days: Math.max(1, retentionDays),
      keep_remarkable_raw: keepRemarkableRaw,
      analytics_version: preferences?.analytics_version ?? DEFAULT_PREFERENCES.analytics_version,
      live_coaching_mode: liveCoachingMode,
      capture_toggles: {
        ...captureToggles,
        camera: true,
        screen: false,
      },
      default_manual_tags: sanitizeManualTags(manualTags),
    });
    setPreferences(nextPreferences);
    setError(null);
  }

  async function toggleSessionRemarkable(nextValue: boolean) {
    if (!reviewSessionId) {
      return;
    }
    const note =
      nextValue
        ? normalizeText(window.prompt("Why is this session remarkable?", sessionAnalytics?.remarkable_moments.find((moment) => moment.session_level)?.note ?? "") ?? "")
        : null;
    const updated = await markSessionRemarkable(reviewSessionId, {
      remarkable: nextValue,
      note,
    });
    if (session?.session_id === updated.session_id) {
      setSession(updated);
    }
    await refreshSessionLibrary(updated.session_id);
    await refreshAnalyticsViews();
  }

  async function toggleMomentRemarkable(review: ReviewEntry) {
    if (!reviewSessionId) {
      return;
    }
    if (review.remarkable) {
      const updated = await clearMomentRemarkable(reviewSessionId, review.sequence);
      if (session?.session_id === updated.session_id) {
        setSession(updated);
      }
      await refreshSessionLibrary(updated.session_id);
      await refreshAnalyticsViews();
      return;
    }

    const note = normalizeText(
      window.prompt(
        `Why is review ${review.sequence} remarkable?`,
        review.remarkable_note ?? "",
      ) ?? "",
    );
    const updated = await markMomentRemarkable(reviewSessionId, review.sequence, {
      remarkable: true,
      note,
    });
    if (session?.session_id === updated.session_id) {
      setSession(updated);
    }
    await refreshSessionLibrary(updated.session_id);
    await refreshAnalyticsViews();
  }

  function orbImageStyle(label: FocusLabel): React.CSSProperties {
    const images = orbImages[label];
    if (!images.length) {
      return {};
    }
    const index = orbCycleIndexRef.current[label] % images.length;
    return {
      backgroundImage: `url(${images[index]})`,
      backgroundSize: "cover",
      backgroundPosition: "center",
    };
  }

  function openDockTab(tab: DockTab) {
    setActiveDockTab(tab);
    window.scrollTo({
      top: 0,
      behavior: "smooth",
    });
    debugLog("dock tab opened", { tab });
  }

  const currentLabel = session?.current_label ?? "focused";
  const currentAnalysisMode = session?.analysis_mode ?? analysisMode;
  const currentLabelClass = LABEL_STYLES[currentLabel];
  const currentDisplayLabel = displayLabel(currentLabel, currentAnalysisMode);
  const currentDisplayReason = visibleNote(
    currentLabel,
    session?.short_reason ?? "Waiting for the first review.",
    currentAnalysisMode,
  );
  const temporaryExpiry = formatExpiry(session?.temporary_expires_at);
  const reviewChip = reviewStatusCopy(session?.review_status);
  const selectedTimeline =
    reviewTimelineMode === "rescan" && reviewDetail?.rescan_timeline.length
      ? reviewDetail.rescan_timeline
      : (reviewDetail?.live_timeline ?? []);
  const reviewMoments = selectedTimeline.slice(-12).reverse();
  const focusMetrics = sessionAnalytics?.metrics ?? null;
  const focusInsights = sessionAnalytics?.insights ?? [];
  const remarkableMoments = sessionAnalytics?.remarkable_moments ?? [];
  const privacyLedger = sessionAnalytics?.privacy_ledger ?? session?.capture_toggles ?? captureToggles;

  const startBlocker =
    session?.status === "paused"
      ? null
      : !setup?.ready
        ? (setup?.message ?? "Model is not ready yet")
        : !cameraStream
          ? "Enable the camera to start the live buddy."
          : includeScreenAnalysis && !screenStream
            ? "Turn off screen analysis or enable screen capture to start."
            : null;

  const startDisabled = busy !== null || session?.status === "running" || startBlocker !== null;
  const pauseDisabled = busy !== null || session?.status !== "running";
  const endDisabled = busy !== null || !session || session.status === "stopped";
  const saveDisabled = busy !== null || !session || session.is_saved;
  const rescanDisabled = busy !== null || !session || !session.can_rescan;
  const selectedSessionRemarkable = reviewDetail?.session.remarkable ?? false;
  const settingsDirty =
    preferences === null ||
    JSON.stringify({
      raw_retention_days: retentionDays,
      keep_remarkable_raw: keepRemarkableRaw,
      live_coaching_mode: liveCoachingMode,
      capture_toggles: { ...captureToggles, camera: true, screen: false },
      default_manual_tags: sanitizeManualTags(manualTags),
    }) !==
      JSON.stringify({
        raw_retention_days: preferences.raw_retention_days,
        keep_remarkable_raw: preferences.keep_remarkable_raw,
        live_coaching_mode: preferences.live_coaching_mode,
        capture_toggles: { ...preferences.capture_toggles, camera: true, screen: false },
        default_manual_tags: sanitizeManualTags(preferences.default_manual_tags),
      });

  return (
    <main className="buddy-shell">
      <div className="buddy-backdrop buddy-backdrop-one" />
      <div className="buddy-backdrop buddy-backdrop-two" />

      <div
        ref={liveSectionRef}
        className={`dock-anchor-section ${activeDockTab === "live" ? "active" : "hidden"}`}
        data-dock-section="live"
      >
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
              {setup?.ready ? "Model ready" : "Setup needed"}
            </span>
          </div>
          <p className="setup-message">{setup?.message ?? "Checking local model setup..."}</p>
          <label className="field">
            <span>Session name</span>
            <input
              value={sessionName}
              onChange={(event) => setSessionName(event.target.value)}
              placeholder="Focus Buddy Session"
            />
          </label>
          <div className="button-stack">
            <button onClick={() => void withBusy("Requesting camera", enableCamera)} disabled={!!cameraStream}>
              {cameraStream ? "Camera ready" : "Enable camera"}
            </button>
            {includeScreenAnalysis ? (
              <button
                onClick={() => void withBusy("Requesting screen", enableScreen)}
                disabled={!!screenStream}
              >
                {screenStream ? "Screen ready" : "Enable screen"}
              </button>
            ) : null}
          </div>
          <details className="mini-disclosure">
            <summary>Session options</summary>
            <div className="mini-disclosure-content">
              <div className="field">
                <span>Model</span>
                <div className="review-toggle-row compact-toggle-row">
                  <button
                    className={`toggle-pill ${runtimeProfile === "standard" ? "selected" : ""}`}
                    onClick={() => setRuntimeProfile("standard")}
                    disabled={session?.status === "running" || session?.status === "paused" || (!!setup && !setup.available_runtime_profiles.includes("standard"))}
                  >
                    Standard
                  </button>
                  <button
                    className={`toggle-pill ${runtimeProfile === "higher_accuracy" ? "selected" : ""}`}
                    onClick={() => setRuntimeProfile("higher_accuracy")}
                    disabled={session?.status === "running" || session?.status === "paused" || (!!setup && !setup.available_runtime_profiles.includes("higher_accuracy"))}
                  >
                    Accurate
                  </button>
                  <button
                    className={`toggle-pill ${runtimeProfile === "edge" ? "selected" : ""}`}
                    onClick={() => setRuntimeProfile("edge")}
                    disabled={session?.status === "running" || session?.status === "paused" || (!!setup && !setup.available_runtime_profiles.includes("edge"))}
                  >
                    Edge
                  </button>
                </div>
              </div>
              <div className="field">
                <span>Review style</span>
                <div className="review-toggle-row compact-toggle-row">
                  <button
                    className={`toggle-pill ${analysisMode === "classification" ? "selected" : ""}`}
                    onClick={() => setAnalysisMode("classification")}
                    disabled={session?.status === "running" || session?.status === "paused"}
                  >
                    Focused / unfocused
                  </button>
                  <button
                    className={`toggle-pill ${analysisMode === "annotation" ? "selected" : ""}`}
                    onClick={() => setAnalysisMode("annotation")}
                    disabled={session?.status === "running" || session?.status === "paused"}
                  >
                    Annotation
                  </button>
                </div>
              </div>
              <div className="field">
                <span>Live coaching</span>
                <div className="review-toggle-row compact-toggle-row">
                  {(["off", "notifications", "ambient", "full"] as LiveCoachingMode[]).map((mode) => (
                    <button
                      key={mode}
                      className={`toggle-pill ${liveCoachingMode === mode ? "selected" : ""}`}
                      onClick={() => setLiveCoachingMode(mode)}
                      disabled={session?.status === "running" || session?.status === "paused"}
                    >
                      {liveCoachingCopy(mode)}
                    </button>
                  ))}
                </div>
              </div>
              <label className="toggle-row">
                <input
                  type="checkbox"
                  checked={includeScreenAnalysis}
                  onChange={(event) => setIncludeScreenAnalysis(event.target.checked)}
                  disabled={session?.status === "running" || session?.status === "paused"}
                />
                <span>Include screen analysis this session</span>
              </label>
            </div>
          </details>
          {startBlocker ? (
            <p className="inline-note">{startBlocker}</p>
          ) : (
            <p className="inline-note">
              {analysisMode === "classification"
                ? "Ready to start with binary focus classification and deterministic nudges."
                : "Ready to start with model-written annotations and local analytics."}
            </p>
          )}
        </section>

        <section className="buddy-card companion-card">
          <div className="section-header">
            <h2>Buddy</h2>
            <div className="header-actions">
              <label className="tiny-toggle">
                <input
                  type="checkbox"
                  checked={showBubble}
                  onChange={(event) => setShowBubble(event.target.checked)}
                />
                <span>Always-on orb</span>
              </label>
              <label className="tiny-toggle">
                <input
                  type="checkbox"
                  checked={desktopNudges}
                  onChange={(event) => setDesktopNudges(event.target.checked)}
                />
                <span>Desktop nudges</span>
              </label>
              <span className={`status-chip ${reviewChip.tone}`}>{reviewChip.label}</span>
            </div>
          </div>
          <div className="buddy-stage">
            <div className={`buddy-orb ${currentLabelClass}`} style={orbImageStyle(currentLabel)}>
              <div className="buddy-eye left" />
              <div className="buddy-eye right" />
              <div className="buddy-mouth" />
            </div>
            <div className="buddy-copy">
              <p className="label-line">{currentDisplayLabel}</p>
              <p className="reason-line">{currentDisplayReason}</p>
              <p className="message-line">
                {session?.companion_message ?? "I’ll stay local, gentle, and evidence-based."}
              </p>
            </div>
          </div>
          <details className="mini-disclosure orb-disclosure">
            <summary>Customize orb appearance</summary>
            <div className="mini-disclosure-content orb-appearance">
              <div className="orb-label-grid">
                {FOCUS_LABELS.map((label) => (
                  <div key={label} className="orb-label-slot">
                    <span className="orb-slot-name">{labelCopy(label)}</span>
                    <div className="orb-thumbs">
                      {orbImages[label].map((src, index) => (
                        <div key={index} className="orb-thumb-wrap">
                          <img src={src} alt={`${label} orb ${index + 1}`} className="orb-thumb" />
                          <button
                            className="orb-thumb-remove"
                            onClick={() => handleOrbImageRemove(label, index)}
                            title="Remove image"
                          >
                            ×
                          </button>
                        </div>
                      ))}
                      <label className="orb-upload-btn" title={`Upload orb image for ${label}`}>
                        <input
                          type="file"
                          accept="image/*"
                          multiple
                          style={{ display: "none" }}
                          onChange={(event) => handleOrbImageUpload(label, event.target.files)}
                        />
                        +
                      </label>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </details>
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
            <button
              onClick={() => void withBusy("Starting session", startOrResumeSession)}
              disabled={startDisabled}
            >
              {session?.status === "paused" ? "Resume" : "Start"}
            </button>
            <button onClick={() => void withBusy("Pausing session", pauseSession)} disabled={pauseDisabled}>
              Pause
            </button>
            <button onClick={() => void withBusy("Ending session", endSession)} disabled={endDisabled}>
              End
            </button>
            <button onClick={() => void withBusy("Saving session", saveCurrentSession)} disabled={saveDisabled}>
              {session?.is_saved ? "Saved" : "Save session"}
            </button>
            <button onClick={() => void withBusy("Running rescan", runRescan)} disabled={rescanDisabled}>
              Rescan session
            </button>
            <button
              className="secondary-pill"
              onClick={() => void withBusy("Capturing context", async () => {
                await captureContextNow("manual");
              })}
              disabled={!session || session.status !== "running"}
            >
              Capture context now
            </button>
          </div>
          <div className="meta-stack">
            <p>{busy ?? (startBlocker ?? "Ready when you are.")}</p>
            {session?.last_review_at ? <p>Last review: {formatTime(session.last_review_at)}</p> : null}
            {temporaryExpiry ? <p>Temporary keyframes expire at {temporaryExpiry} unless you save.</p> : null}
            <p>
              Live coaching: {liveCoachingCopy(session?.live_coaching_mode ?? liveCoachingMode)}
              {soundMonitorEnabled ? " · sound meter active" : ""}
            </p>
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
                      <strong>{displayLabel(review.label, currentAnalysisMode)}</strong>
                      <p>{visibleNote(review.label, review.note, currentAnalysisMode)}</p>
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
          {session && <FocusRibbon summary={session.summary} />}
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
            <article>
              <p>Keyframes</p>
              <strong>{session?.keyframe_count ?? 0}</strong>
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
      </div>

      <div
        ref={analyticsSectionRef}
        className={`dock-anchor-section ${activeDockTab === "analytics" ? "active" : "hidden"}`}
        data-dock-section="analytics"
      >
        <SectionHero
          eyebrow="Stats"
          title="Your local analytics."
          copy="Review today’s signals and weekly patterns without leaving the private capture loop on your Mac."
        />
        <DisclosureCard
          title="Today"
          badge={
            <span className="status-chip idle">
              {todayAnalytics ? formatPercent(todayAnalytics.today.avg_focus_ratio) : "No data"}
            </span>
          }
          storageKey="focus-buddy-section-today"
          defaultOpen={true}
          className="analytics-card"
        >
        {todayAnalytics ? (
          <>
            <div className="analytics-grid">
              <MetricTile
                label="Focused time"
                value={formatDuration(todayAnalytics.today.total_focused_ms)}
                detail={`${todayAnalytics.today.session_count} sessions`}
              />
              <MetricTile
                label="Unfocused time"
                value={formatDuration(todayAnalytics.today.total_unfocused_ms)}
                detail={todayAnalytics.today.avg_recovery_ms ? `Recovery ${formatDuration(todayAnalytics.today.avg_recovery_ms)}` : "Recovery not measured yet"}
              />
            </div>
            <div className="hour-blocks">
              <div>
                <p className="subsection-title">Best hours</p>
                <ComparisonList
                  points={todayAnalytics.today.best_hour_blocks.map((block) => ({
                    dimension: "hour",
                    key: formatHourLabel(block.hour),
                    sample_size: block.sample_size,
                    session_count: block.sample_size,
                    avg_focus_ratio: block.focus_ratio,
                    avg_recovery_ms: null,
                    avg_session_length_ms: 0,
                    confidence: block.sample_size >= 6 ? "high" : block.sample_size >= 3 ? "medium" : "low",
                  }))}
                  emptyCopy="Finish a few sessions to surface strong hours."
                />
              </div>
              <div>
                <p className="subsection-title">Top contexts</p>
                <ComparisonList
                  points={todayAnalytics.today.top_contexts}
                  emptyCopy="Turn on context capture to compare environments."
                />
              </div>
            </div>
            <InsightList
              insights={todayAnalytics.today.insights}
              emptyCopy="Today’s insights will appear after a few meaningful sessions."
            />
          </>
        ) : (
          <div className="empty-state">Today’s rollup will appear after the first reviewed session.</div>
        )}
        </DisclosureCard>

        <DisclosureCard
          title="Trends"
          badge={
            <span className="status-chip idle">
              {weekAnalytics ? weekAnalytics.week.session_count : 0} sessions
            </span>
          }
          storageKey="focus-buddy-section-trends"
          className="analytics-card"
        >
        {weekAnalytics ? (
          <>
            <div className="analytics-grid">
              <MetricTile
                label="Weekly focus"
                value={formatPercent(weekAnalytics.week.avg_focus_ratio)}
                detail={`${weekAnalytics.week.week_id}`}
              />
              <MetricTile
                label="Recovery"
                value={weekAnalytics.week.avg_recovery_ms ? formatDuration(weekAnalytics.week.avg_recovery_ms) : "n/a"}
                detail={
                  weekAnalytics.week.consistency_delta !== null && weekAnalytics.week.consistency_delta !== undefined
                    ? `Delta ${formatPercent(weekAnalytics.week.consistency_delta)}`
                    : "Need another week for deltas"
                }
              />
            </div>
            <div className="hour-blocks">
              <div>
                <p className="subsection-title">Best conditions</p>
                <ComparisonList
                  points={weekAnalytics.week.best_conditions}
                  emptyCopy="Need more context-rich sessions to identify best conditions."
                />
              </div>
              <div>
                <p className="subsection-title">Weakest conditions</p>
                <ComparisonList
                  points={weekAnalytics.week.weakest_conditions}
                  emptyCopy="Weak spots appear once multiple conditions are sampled."
                />
              </div>
            </div>
            <InsightList
              insights={weekAnalytics.week.insights}
              emptyCopy="Weekly insights will appear after more than one meaningful session."
            />
          </>
        ) : (
          <div className="empty-state">Weekly trends will appear once you’ve built a local history.</div>
        )}
        </DisclosureCard>
      </div>

      <div
        ref={reviewSectionRef}
        className={`dock-anchor-section ${activeDockTab === "review" ? "active" : "hidden"}`}
        data-dock-section="review"
      >
        <SectionHero
          eyebrow="Review"
          title="Saved moments and time-lapse."
          copy="Jump into keyframes, timeline notes, and after-session playback instead of digging through one long feed."
        />
        <DisclosureCard
          title="Saved moments"
          badge={<span className="status-chip idle">{sessions.length} sessions</span>}
          storageKey="focus-buddy-section-saved-moments"
          className="library-card"
        >
        <p className="setup-message">
          Review saved moments after the fact through keyframes, timeline notes, rescans, and analytics. Focus Buddy does not store full continuous video.
        </p>
        <div className="library-list">
          {sessions.length ? (
            sessions.map((candidate) => (
              <button
                key={candidate.session_id}
                className={`library-item ${reviewSessionId === candidate.session_id ? "selected" : ""}`}
                onClick={() =>
                  void withBusy("Loading session review", async () => {
                    setReviewTimelineMode("live");
                    setReviewSessionId(candidate.session_id);
                    await refreshSessionLibrary(candidate.session_id);
                  })
                }
                disabled={busy !== null}
              >
                <span className="library-title">
                  {candidate.session_name}
                  {candidate.remarkable ? " · Remarkable" : ""}
                </span>
                <span className="library-meta">
                  {formatSessionStamp(candidate.created_at)} · {candidate.summary.total_reviews} reviews ·{" "}
                  {candidate.keyframe_count} keyframes
                </span>
              </button>
            ))
          ) : (
            <div className="empty-state">Finish a session and save it to review the timeline later.</div>
          )}
        </div>
        </DisclosureCard>

        <DisclosureCard
          title="After-session review"
          badge={
            <span className="status-chip idle">
              {reviewDetail ? `${selectedTimeline.length} moments` : "No session selected"}
            </span>
          }
          storageKey="focus-buddy-section-review"
          defaultOpen={Boolean(reviewDetail)}
          className="review-card"
        >
        {reviewDetail ? (
          <>
            <p className="setup-message">
              {reviewDetail.session.session_name} · {formatSessionStamp(reviewDetail.session.created_at)}
            </p>
            <div className="review-action-row">
              <button
                className={`secondary-pill remarkable-button ${selectedSessionRemarkable ? "selected" : ""}`}
                onClick={() =>
                  void withBusy(
                    selectedSessionRemarkable ? "Clearing remarkable flag" : "Marking session remarkable",
                    () => toggleSessionRemarkable(!selectedSessionRemarkable),
                  )
                }
              >
                {selectedSessionRemarkable ? "Remarkable" : "Mark remarkable"}
              </button>
            </div>
            {focusMetrics ? (
              <>
                <div className="analytics-grid">
                  <MetricTile
                    label="Longest focus streak"
                    value={formatDuration(focusMetrics.longest_focus_streak_ms)}
                    detail={`${formatPercent(focusMetrics.focus_ratio)} focused`}
                  />
                  <MetricTile
                    label="Recoveries"
                    value={String(focusMetrics.recovery_count)}
                    detail={focusMetrics.avg_recovery_ms ? `Avg ${formatDuration(focusMetrics.avg_recovery_ms)}` : "Not enough recoveries yet"}
                  />
                  <MetricTile
                    label="Nudge effectiveness"
                    value={formatPercent(focusMetrics.nudge_effectiveness_rate)}
                    detail={`${focusMetrics.nudge_count} nudges`}
                  />
                  <MetricTile
                    label="Context captures"
                    value={String(focusMetrics.context_capture_count)}
                    detail={`${focusMetrics.label_transition_count} transitions`}
                  />
                </div>
                <InsightList
                  insights={focusInsights}
                  emptyCopy="Session insights will appear once a clear pattern forms."
                />
              </>
            ) : null}
            <div className="review-toggle-row">
              <button
                className={`toggle-pill ${reviewTimelineMode === "live" ? "selected" : ""}`}
                onClick={() => setReviewTimelineMode("live")}
              >
                Live review
              </button>
              {reviewDetail.rescan_timeline.length ? (
                <button
                  className={`toggle-pill ${reviewTimelineMode === "rescan" ? "selected" : ""}`}
                  onClick={() => setReviewTimelineMode("rescan")}
                >
                  Rescan
                </button>
              ) : null}
            </div>
            <div className="review-action-row">
              <button className="secondary-pill" onClick={() => setOverlayMode("timelapse")}>
                Watch Time-lapse
              </button>
              <button className="secondary-pill" onClick={() => setOverlayMode("cinematic")}>
                Cinematic Snippet
              </button>
            </div>
            <p className="inline-note">
              Time-lapse playback is built from frequent saved snapshots, context captures, and review entries, not full continuous video.
            </p>
            <div className="review-list">
              {reviewMoments.length ? (
                reviewMoments.map((review) => {
                  const previewSrc = keyframeSrc(reviewDetail.session.session_id, review.keyframe_path);
                  return (
                    <article key={`${review.mode}-${review.sequence}-${review.timestamp}`} className="review-item">
                      {previewSrc ? (
                        <img
                          src={previewSrc}
                          alt={`Keyframe for ${displayLabel(review.label, reviewDetail.session.analysis_mode)} at ${formatTime(review.timestamp)}`}
                          className="review-thumb"
                        />
                      ) : (
                        <div className="review-thumb review-thumb-empty">No keyframe</div>
                      )}
                      <div className="review-copy">
                        <div className="review-topline">
                          <strong>{displayLabel(review.label, reviewDetail.session.analysis_mode)}</strong>
                          <span>{formatTime(review.timestamp)}</span>
                        </div>
                        <p>{visibleNote(review.label, review.note, reviewDetail.session.analysis_mode)}</p>
                        <p className="review-buddy-note">{review.buddy_note}</p>
                        <p className="review-reasons">{reasonsCopy(review.reasons)}</p>
                        {review.remarkable_note ? (
                          <p className="review-remarkable-note">Remarkable: {review.remarkable_note}</p>
                        ) : null}
                        <div className="review-actions">
                          <button
                            className={`secondary-pill remarkable-button ${review.remarkable ? "selected" : ""}`}
                            onClick={() =>
                              void withBusy(
                                review.remarkable ? "Clearing moment flag" : "Marking moment remarkable",
                                () => toggleMomentRemarkable(review),
                              )
                            }
                          >
                            {review.remarkable ? "Remarkable" : "Mark moment"}
                          </button>
                        </div>
                      </div>
                    </article>
                  );
                })
              ) : (
                <div className="empty-state">No review moments are available for this timeline yet.</div>
              )}
            </div>
          </>
        ) : (
          <div className="empty-state">Select a finished session to review saved moments after the fact.</div>
        )}
        </DisclosureCard>
      </div>

      <div
        ref={patternsSectionRef}
        className={`dock-anchor-section ${activeDockTab === "patterns" ? "active" : "hidden"}`}
        data-dock-section="patterns"
      >
        <SectionHero
          eyebrow="Patterns"
          title="Compare conditions."
          copy="Surface environmental signals, experiments, and remarkable sessions as their own layer instead of mixing them into live coaching."
        />
        <DisclosureCard
          title="Patterns"
          badge={<span className="status-chip idle">{globalInsights.length} insights</span>}
          storageKey="focus-buddy-section-patterns"
          className="analytics-card"
        >
        <InsightList
          insights={globalInsights}
          emptyCopy="As local history grows, Focus Buddy will surface pattern cards here."
        />
        </DisclosureCard>

        <DisclosureCard
          title="Experiments"
          badge={
            <span className="status-chip idle">
              {experimentAnalytics ? experimentAnalytics.dimensions.length : 0} dimensions
            </span>
          }
          storageKey="focus-buddy-section-experiments"
          className="analytics-card"
        >
        {experimentAnalytics ? (
          <div className="experiment-grid">
            {experimentAnalytics.dimensions.map((dimension) => (
              <div key={dimension.dimension} className="experiment-column">
                <p className="subsection-title">{prettifyKey(dimension.dimension)}</p>
                <ComparisonList
                  points={dimension.comparisons}
                  emptyCopy="Not enough samples for this comparison yet."
                />
              </div>
            ))}
          </div>
        ) : (
          <div className="empty-state">Experiment comparisons will appear once context capture is enabled.</div>
        )}
        </DisclosureCard>

        <DisclosureCard
          title="Remarkable"
          badge={<span className="status-chip idle">{remarkableMoments.length} saved highlights</span>}
          storageKey="focus-buddy-section-remarkable"
          className="analytics-card"
        >
        {remarkableMoments.length ? (
          <div className="remarkable-list">
            {remarkableMoments.map((moment, index) => (
              <article key={`${moment.sequence ?? "session"}-${index}`} className="remarkable-item">
                <strong>{moment.session_level ? "Session highlight" : `Moment ${moment.sequence}`}</strong>
                <p>{moment.note ?? "Marked as remarkable for retention."}</p>
                <span>
                  {moment.keyframe_path ? moment.keyframe_path.split("/").pop() : "No dedicated keyframe"}
                </span>
              </article>
            ))}
          </div>
        ) : (
          <div className="empty-state">
            Mark a session or moment as remarkable to keep raw evidence beyond the retention window.
          </div>
        )}
        </DisclosureCard>
      </div>

      <div
        ref={settingsSectionRef}
        className={`dock-anchor-section ${activeDockTab === "settings" ? "active" : "hidden"}`}
        data-dock-section="settings"
      >
        <SectionHero
          eyebrow="Settings"
          title="Privacy and capture defaults."
          copy="Control what gets collected, how long raw evidence stays around, and which sources stay off unless you opt in."
        />
        <DisclosureCard
          title="Settings"
          badge={
            <span className={`status-chip ${settingsDirty ? "warn" : "ok"}`}>
              {settingsDirty ? "Unsaved" : "Saved"}
            </span>
          }
          storageKey="focus-buddy-section-settings"
          className="analytics-card"
        >
        <div className="settings-grid">
          <div className="settings-group">
            <p className="subsection-title">Privacy and retention</p>
            <label className="field">
              <span>Raw evidence retention (days)</span>
              <input
                type="number"
                min={1}
                max={30}
                value={retentionDays}
                onChange={(event) => setRetentionDays(Number(event.target.value) || 7)}
              />
            </label>
            <label className="toggle-row">
              <input
                type="checkbox"
                checked={keepRemarkableRaw}
                onChange={(event) => setKeepRemarkableRaw(event.target.checked)}
              />
              <span>Keep raw evidence for remarkable sessions and moments</span>
            </label>
          </div>

          <div className="settings-group">
            <p className="subsection-title">Capture sources</p>
            <div className="settings-toggle-list">
              {(Object.keys(DEFAULT_CAPTURE_TOGGLES) as (keyof DataSourceToggles)[]).map((key) => (
                <label key={key} className="toggle-row">
                  <input
                    type="checkbox"
                    checked={key === "camera" ? true : captureToggles[key]}
                    onChange={(event) => {
                      if (key === "camera") {
                        return;
                      }
                      setCaptureToggles((current) => ({
                        ...current,
                        [key]: event.target.checked,
                      }));
                    }}
                    disabled={key === "camera" || session?.status === "running" || session?.status === "paused"}
                  />
                  <span>{contextToggleCopy(key)}</span>
                </label>
              ))}
            </div>
            <p className="inline-note">
              Sound features store local audio levels only, never raw audio. Calendar context remains best-effort and may stay empty until the desktop bridge gains access.
            </p>
          </div>

          <div className="settings-group settings-group-wide">
            <p className="subsection-title">Default manual tags</p>
            <div className="manual-tags-grid">
              <label className="field">
                <span>Task</span>
                <input
                  value={manualTags.task ?? ""}
                  onChange={(event) =>
                    setManualTags((current) => ({ ...current, task: event.target.value }))
                  }
                  placeholder="Writing, coding, studying"
                />
              </label>
              <label className="field">
                <span>Location</span>
                <input
                  value={manualTags.location_label ?? ""}
                  onChange={(event) =>
                    setManualTags((current) => ({ ...current, location_label: event.target.value }))
                  }
                  placeholder="Home desk, library, cafe"
                />
              </label>
              <label className="field">
                <span>Environment</span>
                <input
                  value={manualTags.environment ?? ""}
                  onChange={(event) =>
                    setManualTags((current) => ({ ...current, environment: event.target.value }))
                  }
                  placeholder="Quiet, music, busy room"
                />
              </label>
              <label className="field">
                <span>Mood</span>
                <input
                  value={manualTags.mood ?? ""}
                  onChange={(event) =>
                    setManualTags((current) => ({ ...current, mood: event.target.value }))
                  }
                  placeholder="Calm, tired, restless"
                />
              </label>
              <label className="field">
                <span>Energy</span>
                <input
                  value={manualTags.energy ?? ""}
                  onChange={(event) =>
                    setManualTags((current) => ({ ...current, energy: event.target.value }))
                  }
                  placeholder="High, medium, low"
                />
              </label>
              <label className="field">
                <span>Caffeine</span>
                <input
                  value={manualTags.caffeine ?? ""}
                  onChange={(event) =>
                    setManualTags((current) => ({ ...current, caffeine: event.target.value }))
                  }
                  placeholder="Coffee, tea, none"
                />
              </label>
              <label className="field manual-note-field">
                <span>Note</span>
                <input
                  value={manualTags.note ?? ""}
                  onChange={(event) =>
                    setManualTags((current) => ({ ...current, note: event.target.value }))
                  }
                  placeholder="Anything relevant about this context"
                />
              </label>
              <label className="toggle-row">
                <input
                  type="checkbox"
                  checked={manualTags.phone_present ?? false}
                  onChange={(event) =>
                    setManualTags((current) => ({
                      ...current,
                      phone_present: event.target.checked,
                    }))
                  }
                />
                <span>Phone visible during this work context</span>
              </label>
            </div>
          </div>

          <div className="settings-group settings-group-wide">
            <p className="subsection-title">Privacy ledger</p>
            <div className="privacy-ledger">
              {(Object.entries(privacyLedger) as [keyof DataSourceToggles, boolean][]).map(([key, enabled]) => (
                <div key={key} className="privacy-row">
                  <span>{contextToggleCopy(key)}</span>
                  <span className={`tiny-chip ${enabled ? "ok" : "idle"}`}>
                    {enabled ? "On" : "Off"}
                  </span>
                </div>
              ))}
              <div className="privacy-row">
                <span>Device source</span>
                <span className="tiny-chip idle">Mac primary · iPhone-ready schema</span>
              </div>
            </div>
          </div>
        </div>
        <div className="review-action-row">
          <button onClick={() => void withBusy("Saving settings", saveAnalyticsSettings)} disabled={busy !== null}>
            Save settings
          </button>
        </div>
        <p className="inline-note">
          New settings apply to the next session. Existing sessions keep the capture policy they started with.
        </p>
        </DisclosureCard>
      </div>

      <nav className="buddy-bottom-nav" aria-label="Primary sections">
        {(["live", "analytics", "review", "patterns", "settings"] as DockTab[]).map((tab) => (
          <button
            key={tab}
            type="button"
            className={`bottom-nav-item ${activeDockTab === tab ? "active" : ""}`}
            onClick={() => openDockTab(tab)}
            aria-label={dockTabCopy(tab)}
            aria-current={activeDockTab === tab ? "page" : undefined}
          >
            <span className="bottom-nav-icon">
              <DockIcon tab={tab} />
            </span>
            <span className="bottom-nav-label">{dockTabCopy(tab)}</span>
          </button>
        ))}
      </nav>

      {overlayMode && reviewDetail ? (
        <ReviewOverlay
          session={reviewDetail.session}
          timeline={selectedTimeline}
          mode={overlayMode}
          onClose={() => setOverlayMode(null)}
        />
      ) : null}
    </main>
  );
}
