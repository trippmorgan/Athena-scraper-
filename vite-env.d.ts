/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_EXTENSION_ID: string;
  readonly VITE_API_BASE_URL: string;
  readonly VITE_WS_URL: string;
  readonly VITE_API_TIMEOUT_MS: string;
  readonly VITE_API_MAX_RETRIES: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

// Chrome extension API types (for communication with extension)
declare namespace chrome {
  namespace runtime {
    function sendMessage(
      extensionId: string,
      message: any,
      callback?: (response: any) => void
    ): void;
    const lastError: { message: string } | undefined;
  }
}
