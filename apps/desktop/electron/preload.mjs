import { contextBridge, ipcRenderer } from "electron";
import { pathToFileURL } from "node:url";

contextBridge.exposeInMainWorld("desktopShell", {
  platform: process.platform,
  versions: process.versions,
  fileUrl: (absolutePath) => pathToFileURL(absolutePath).toString(),
  apiRequest: (requestInit) => ipcRenderer.invoke("focus-buddy:api-request", requestInit),
});
