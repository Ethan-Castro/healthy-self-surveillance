import { contextBridge, ipcRenderer } from "electron";
import { pathToFileURL } from "node:url";

contextBridge.exposeInMainWorld("desktopShell", {
  platform: process.platform,
  versions: process.versions,
  fileUrl: (absolutePath) => pathToFileURL(absolutePath).toString(),
  apiRequest: (requestInit) => ipcRenderer.invoke("focus-buddy:api-request", requestInit),
  toggleBubble: (enabled) => ipcRenderer.invoke("focus-buddy:toggle-bubble", { enabled }),
  notify: (payload) => ipcRenderer.invoke("focus-buddy:notify", payload),
  getDesktopContext: () => ipcRenderer.invoke("focus-buddy:get-desktop-context"),
  debugLog: (message, details) => ipcRenderer.invoke("focus-buddy:debug-log", { message, details }),
});
