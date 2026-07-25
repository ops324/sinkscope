import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";

// React.StrictModeは意図的にeffectを2回実行し副作用の不整合を検出するが、
// MapLibre GL(react-map-gl)のようにDOM上に一度きりのWebGLコンテキストを直接
// 構築するライブラリはこの二重マウントに対応しておらず、スタイルの読み込みが
// "Style is not done loading" ループに陥って基図が描画されない不具合を実際に
// 引き起こした(開発時のみの問題。本番ビルドではStrictModeの二重実行自体が
// 発生しないため影響しない)。地図ライブラリを直接組み込む場合の一般的な回避策
// として、ここではStrictModeを外している。
ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(<App />);
