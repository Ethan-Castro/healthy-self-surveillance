import { Notification, app, BrowserWindow, ipcMain, powerMonitor, screen } from "electron";
import { execFile } from "node:child_process";
import path from "node:path";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const DEBUG_PREFIX = "[Focus Buddy Debug]";
const execFileAsync = promisify(execFile);

let mainWindow = null;
let bubbleWindow = null;
let bubbleDraggedByUser = false;

function formatDebugDetails(details) {
  if (details === undefined) {
    return "";
  }
  try {
    return ` ${JSON.stringify(details)}`;
  } catch {
    return ` ${String(details)}`;
  }
}

function debugLog(message, details) {
  console.log(`${DEBUG_PREFIX} ${message}${formatDebugDetails(details)}`);
}

async function readDesktopContext() {
  const idleSeconds = powerMonitor.getSystemIdleTime();
  const idleState = powerMonitor.getSystemIdleState(60);
  if (process.platform !== "darwin") {
    return {
      appName: null,
      windowTitle: null,
      calendarTitle: null,
      calendarCategory: null,
      systemIdleSeconds: idleSeconds,
      systemIdleState: idleState,
    };
  }

  const script = `
tell application "System Events"
  set frontAppName to ""
  set frontWindowTitle to ""
  try
    set frontApp to first application process whose frontmost is true
    set frontAppName to name of frontApp
    try
      if (count of windows of frontApp) > 0 then
        set frontWindowTitle to name of front window of frontApp
      end if
    end try
  end try
  return frontAppName & linefeed & frontWindowTitle
end tell
`.trim();

  try {
    const { stdout } = await execFileAsync("/usr/bin/osascript", ["-e", script]);
    const [appName = "", windowTitle = ""] = stdout.trimEnd().split(/\r?\n/, 2);
    return {
      appName: appName || null,
      windowTitle: windowTitle || null,
      calendarTitle: null,
      calendarCategory: null,
      systemIdleSeconds: idleSeconds,
      systemIdleState: idleState,
    };
  } catch (error) {
    debugLog("desktop context lookup failed", {
      error: error instanceof Error ? error.message : String(error),
    });
    return {
      appName: null,
      windowTitle: null,
      calendarTitle: null,
      calendarCategory: null,
      systemIdleSeconds: idleSeconds,
      systemIdleState: idleState,
    };
  }
}

function positionBubbleWindow(window) {
  const display =
    mainWindow && !mainWindow.isDestroyed()
      ? screen.getDisplayMatching(mainWindow.getBounds())
      : screen.getPrimaryDisplay();
  const { x, y, width } = display.workArea;
  const [bubbleWidth] = window.getSize();
  const nextX = Math.floor(x + (width - bubbleWidth) / 2);
  const nextY = y + 12;
  window.setPosition(nextX, nextY);
  return {
    displayId: display.id,
    x: nextX,
    y: nextY,
    workArea: display.workArea,
  };
}

ipcMain.handle("focus-buddy:api-request", async (_event, requestInit) => {
  let path = requestInit.url;
  const method = (requestInit.method ?? "GET").toUpperCase();
  try {
    path = new URL(requestInit.url).pathname;
  } catch {
    // Keep the raw URL when parsing fails.
  }

  if (method !== "GET") {
    debugLog("renderer api request", { method, path });
  }

  const response = await fetch(requestInit.url, {
    method: requestInit.method,
    headers: requestInit.headers,
    body: requestInit.body ?? undefined,
  });

  const text = await response.text();
  if (!response.ok) {
    debugLog("renderer api response error", {
      method,
      path,
      status: response.status,
      body: text.slice(0, 240),
    });
  }

  return {
    ok: response.ok,
    status: response.status,
    text,
  };
});

ipcMain.handle("focus-buddy:toggle-bubble", (_event, { enabled }) => {
  debugLog("bubble toggle requested", { enabled });
  if (enabled && !bubbleWindow) {
    createBubbleWindow();
  } else if (!enabled && bubbleWindow) {
    bubbleWindow.close();
    bubbleWindow = null;
    bubbleDraggedByUser = false;
    debugLog("bubble window closed from toggle");
  }
});

ipcMain.handle("focus-buddy:debug-log", (_event, payload) => {
  debugLog(payload.message, payload.details);
});

ipcMain.handle("focus-buddy:notify", (_event, payload) => {
  if (!Notification.isSupported()) {
    debugLog("desktop notification unavailable", payload);
    return { ok: false };
  }

  const notification = new Notification({
    title: payload.title ?? "Focus Buddy",
    body: payload.body ?? "",
    silent: payload.silent ?? false,
  });
  notification.show();
  debugLog("desktop notification shown", payload);
  return { ok: true };
});

ipcMain.handle("focus-buddy:get-desktop-context", async () => {
  const context = await readDesktopContext();
  debugLog("desktop context provided", context);
  return context;
});

function createBubbleWindow() {
  debugLog("creating bubble window");
  bubbleWindow = new BrowserWindow({
    width: 190,
    height: 260,
    show: false,
    resizable: false,
    movable: true,
    frame: false,
    transparent: true,
    backgroundColor: "#00000000",
    alwaysOnTop: true,
    hasShadow: false,
    focusable: false,
    skipTaskbar: true,
    webPreferences: {
      preload: path.join(__dirname, "preload.mjs"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  debugLog("bubble window created", positionBubbleWindow(bubbleWindow));
  bubbleWindow.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  bubbleWindow.setAlwaysOnTop(true, "screen-saver");
  // Mouse events must be enabled so the user can drag the window.
  bubbleWindow.webContents.on("console-message", (_event, _level, message) => {
    debugLog(`bubble renderer ${message}`);
  });

  const revealBubbleWindow = () => {
    if (!bubbleWindow || bubbleWindow.isDestroyed()) {
      return;
    }
    const position = positionBubbleWindow(bubbleWindow);
    bubbleWindow.showInactive();
    bubbleWindow.moveTop();
    debugLog("bubble window reveal attempted", {
      ...position,
      visible: bubbleWindow.isVisible(),
    });
  };

  bubbleWindow.once("ready-to-show", revealBubbleWindow);
  bubbleWindow.webContents.once("did-finish-load", revealBubbleWindow);

  const devServerUrl = process.env.VITE_DEV_SERVER_URL;
  if (devServerUrl) {
    bubbleWindow.loadURL(`${devServerUrl}?mode=bubble`);
  } else {
    const indexPath = path.join(__dirname, "..", "dist", "index.html");
    bubbleWindow.loadURL(`file://${indexPath}?mode=bubble`);
  }

  setTimeout(revealBubbleWindow, 1000);

  bubbleWindow.on("moved", () => {
    bubbleDraggedByUser = true;
    debugLog("bubble window dragged by user");
  });

  bubbleWindow.on("closed", () => {
    debugLog("bubble window closed");
    bubbleWindow = null;
    bubbleDraggedByUser = false;
  });
}

function createWindow() {
  debugLog("creating main window");
  mainWindow = new BrowserWindow({
    width: 460,
    height: 900,
    minWidth: 420,
    minHeight: 760,
    title: "Focus Buddy",
    titleBarStyle: "hiddenInset",
    autoHideMenuBar: true,
    backgroundColor: "#ffffff",
    webPreferences: {
      preload: path.join(__dirname, "preload.mjs"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  const devServerUrl = process.env.VITE_DEV_SERVER_URL;
  if (devServerUrl) {
    mainWindow.loadURL(devServerUrl);
  } else {
    mainWindow.loadFile(path.join(__dirname, "..", "dist", "index.html"));
  }

  const syncBubblePosition = () => {
    if (bubbleWindow && !bubbleWindow.isDestroyed() && !bubbleDraggedByUser) {
      positionBubbleWindow(bubbleWindow);
    }
  };

  mainWindow.on("move", syncBubblePosition);
  mainWindow.on("resize", syncBubblePosition);
  mainWindow.on("show", syncBubblePosition);

  mainWindow.on("closed", () => {
    debugLog("main window closed");
    mainWindow = null;
  });
}

app.whenReady().then(() => {
  debugLog("app ready");
  createWindow();
  createBubbleWindow();
  app.on("activate", () => {
    if (!mainWindow) {
      debugLog("app activate recreating main window");
      createWindow();
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});
