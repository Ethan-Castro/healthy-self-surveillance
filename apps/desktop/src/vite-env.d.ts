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
    };
  }
}

export {};
