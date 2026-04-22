/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Dev: để trống để dùng proxy; prod: URL API đầy đủ */
  readonly VITE_API_BASE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
