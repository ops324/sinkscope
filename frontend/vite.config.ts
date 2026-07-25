import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 単一URL配信(D7): `--mode static`(npm run build:static)のときだけ、GitHub Pages の
// プロジェクトサイト用サブパスを base にする。絶対 base にすることで assets と MapLibre の
// ワーカーURLがサブパス配信でも安定して解決する(相対 "./" だとワーカー読込が壊れうる)。
// Pages のパスが違う場合はこの STATIC_BASE の一定数を変えるだけでよい。
// 通常の dev / build は従来どおり base:"/"(Viteプロキシで /api → :8000)。
const STATIC_BASE = "/sinkscope/";

export default defineConfig(({ mode }) => ({
  base: mode === "static" ? STATIC_BASE : "/",
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
}));
