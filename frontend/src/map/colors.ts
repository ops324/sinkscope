// メッシュ実データの可視化用カラースケール。ハザード判定の閾値ではなく、
// 実測値をそのまま連続的に写像するだけの表示ユーティリティ（予測・スコアは扱わない）。

export type RGBA = [number, number, number, number];

const clamp01 = (t: number) => Math.min(1, Math.max(0, t));
const lerp = (a: number, b: number, t: number) => a + (b - a) * t;

function lerpColor(c0: RGBA, c1: RGBA, t: number): RGBA {
  return [
    Math.round(lerp(c0[0], c1[0], t)),
    Math.round(lerp(c0[1], c1[1], t)),
    Math.round(lerp(c0[2], c1[2], t)),
    Math.round(lerp(c0[3], c1[3], t)),
  ];
}

const NO_DATA_COLOR: RGBA = [70, 76, 84, 50];

/**
 * 変位速度(cm/年)を青(隆起側)〜白〜赤(沈下側)の発散配色に写像する。
 * GSIのInSAR成果図でも広く使われる配色慣行(赤=沈下、青=隆起)に合わせている。
 * これは値の可視化であり、ハザード判定ではない――本AOI平均(-0.072cm/年)は
 * GSI公表精度(概ね±数mm/年)の限界に近く、セル単位の符号は解釈しないこと
 * (HonestyPanelの注記を参照)。
 */
export function velocityColor(value: number | null | undefined, domainHalfWidth = 0.5): RGBA {
  if (value === null || value === undefined || Number.isNaN(value)) return NO_DATA_COLOR;
  const t = clamp01((value + domainHalfWidth) / (2 * domainHalfWidth));
  const blue: RGBA = [33, 102, 172, 140];
  const white: RGBA = [235, 235, 230, 90];
  const red: RGBA = [178, 24, 43, 140];
  return t < 0.5 ? lerpColor(blue, white, t / 0.5) : lerpColor(white, red, (t - 0.5) / 0.5);
}

/** 標高(m)を低地(暖色)〜高地(緑)の連続配色(sequential-diverging)に写像する。 */
export function elevationColor(value: number | null | undefined, min = -8, max = 32): RGBA {
  if (value === null || value === undefined || Number.isNaN(value)) return NO_DATA_COLOR;
  const t = clamp01((value - min) / (max - min));
  const low: RGBA = [140, 81, 10, 150];
  const high: RGBA = [26, 152, 80, 150];
  return lerpColor(low, high, t);
}

/** 道路延長(m)を単一色の濃淡(sequential)に写像する。 */
export function roadLengthColor(value: number | null | undefined, max = 4500): RGBA {
  if (value === null || value === undefined) return NO_DATA_COLOR;
  const t = clamp01(value / max);
  const light: RGBA = [222, 235, 247, 110];
  const dark: RGBA = [8, 81, 156, 165];
  return lerpColor(light, dark, t);
}

/**
 * 土地利用種別コード。国土数値情報 土地利用細分メッシュ(L03-b, 平成21/26/28年度・
 * 令和3年版)のコード表(LandUseCd-09)による。出典:
 * https://nlftp.mlit.go.jp/ksj/gml/codelist/LandUseCd-09.html
 */
export const LAND_USE_LABELS: Record<string, string> = {
  "0100": "田",
  "0200": "その他の農用地",
  "0500": "森林",
  "0600": "荒地",
  "0700": "建物用地",
  "0901": "道路",
  "0902": "鉄道",
  "1000": "その他の用地",
  "1100": "河川地及び湖沼",
  "1400": "海浜",
  "1500": "海水域",
  "1600": "ゴルフ場",
};

const LAND_USE_PALETTE: Record<string, RGBA> = {
  "0100": [247, 218, 100, 150],
  "0200": [253, 191, 111, 150],
  "0500": [76, 153, 76, 150],
  "0600": [191, 191, 133, 150],
  "0700": [217, 95, 82, 150],
  "0901": [140, 140, 140, 150],
  "0902": [90, 90, 90, 150],
  "1000": [180, 180, 180, 150],
  "1100": [102, 166, 217, 150],
  "1400": [230, 216, 173, 150],
  "1500": [49, 106, 156, 150],
  "1600": [140, 196, 120, 150],
};
const LAND_USE_FALLBACK: RGBA = [140, 140, 140, 160];

export function landUseColor(value: string | null | undefined): RGBA {
  if (!value) return NO_DATA_COLOR;
  return LAND_USE_PALETTE[value] ?? LAND_USE_FALLBACK;
}

export function landUseLabel(value: string | null | undefined): string {
  if (!value) return "(データなし)";
  return LAND_USE_LABELS[value] ?? `不明なコード(${value})`;
}

/**
 * Triage点検優先度tier(高/中/低)の配色。連続スコアではなく順序尺度のtierのみを
 * 受け取る点が重要(独立敵対的監査 guardrail (b): キャリブレーション済みに見える
 * 数値を出さない)。実データのMonitorレイヤー(velocityColor等)とは明確に異なる
 * 紫系(Illustrativeの識別)を使い、実データと視覚的に混同されないようにする。
 */
const TIER_COLORS: Record<string, RGBA> = {
  high: [155, 89, 182, 210],
  medium: [155, 89, 182, 140],
  low: [155, 89, 182, 70],
};
const TIER_NO_DATA_COLOR: RGBA = [120, 120, 120, 90];

export function tierColor(tier: string | null | undefined): RGBA {
  if (!tier) return TIER_NO_DATA_COLOR;
  return TIER_COLORS[tier] ?? TIER_NO_DATA_COLOR;
}

export const TIER_LABELS: Record<string, string> = {
  high: "高（相対的な点検候補）",
  medium: "中",
  low: "低",
};
