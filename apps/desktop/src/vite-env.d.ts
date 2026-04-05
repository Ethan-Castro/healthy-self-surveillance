/// <reference types="vite/client" />

declare global {
  interface Window {
    desktopShell?: {
      platform: string;
      versions: Record<string, string>;
    };
  }
}

export {};
