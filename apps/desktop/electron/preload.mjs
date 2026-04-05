import { contextBridge } from "electron";

contextBridge.exposeInMainWorld("desktopShell", {
  platform: process.platform,
  versions: process.versions,
});
