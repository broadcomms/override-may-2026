/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_USE_FIXTURE?: string;
  readonly VITE_API_TARGET?: string;
  readonly VITE_TORCS_RUN_ORIGIN?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
