/// <reference types="vite/client" />

// 単一URL配信(D7)の静的モード切替フラグ。frontend/.env.static で "static" を与える
// (npm run build:static)。未設定の通常dev/buildではライブAPI(/api/)を叩く。
interface ImportMetaEnv {
  readonly VITE_DATA_SOURCE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
