import { app, BrowserWindow, ipcMain } from "electron";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

ipcMain.handle("focus-buddy:api-request", async (_event, requestInit) => {
  const response = await fetch(requestInit.url, {
    method: requestInit.method,
    headers: requestInit.headers,
    body: requestInit.body ?? undefined,
  });

  const text = await response.text();

  return {
    ok: response.ok,
    status: response.status,
    text,
  };
});

function createWindow() {
  const window = new BrowserWindow({
    width: 460,
    height: 900,
    minWidth: 420,
    minHeight: 760,
    title: "Focus Buddy",
    titleBarStyle: "hiddenInset",
    autoHideMenuBar: true,
    backgroundColor: "#f7efe3",
    webPreferences: {
      preload: path.join(__dirname, "preload.mjs"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  const devServerUrl = process.env.VITE_DEV_SERVER_URL;
  if (devServerUrl) {
    window.loadURL(devServerUrl);
  } else {
    window.loadFile(path.join(__dirname, "..", "dist", "index.html"));
  }
}

app.whenReady().then(() => {
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});
