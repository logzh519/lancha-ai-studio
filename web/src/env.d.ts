/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_TARGET?: string
  readonly VITE_ENABLED_MODULES?: string
  readonly VITE_DEV_USER_ID?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
