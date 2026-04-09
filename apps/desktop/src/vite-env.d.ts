/// <reference types="vite/client" />

declare global {
  interface DesktopApiRequest {
    url: string;
    method?: string;
    headers?: Record<string, string>;
    body?: string;
  }

  interface DesktopApiResponse {
    ok: boolean;
    status: number;
    text: string;
  }

  interface Window {
    desktopShell?: {
      platform: string;
      versions: Record<string, string>;
      fileUrl?: (absolutePath: string) => string;
      apiRequest?: (request: DesktopApiRequest) => Promise<DesktopApiResponse>;
      toggleBubble?: (enabled: boolean) => Promise<void>;
      notify?: (payload: { title?: string; body?: string; silent?: boolean }) => Promise<{ ok: boolean }>;
      getDesktopContext?: () => Promise<{
        appName?: string | null;
        windowTitle?: string | null;
        calendarTitle?: string | null;
        calendarCategory?: string | null;
        systemIdleSeconds?: number | null;
        systemIdleState?: string | null;
      }>;
      debugLog?: (message: string, details?: Record<string, unknown>) => Promise<void>;
    };
  }
}

export {};
