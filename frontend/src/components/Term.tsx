import type { ReactNode } from "react";

// 専門用語に、ホバー/フォーカスで平易な補足を出す軽量ツールチップ。
// 初見の読み手向けの補助であり、値そのもの(実測データ)は書き換えない。
// アクセシビリティ: tabIndex/フォーカスでも開き、補足は aria-label に載せる。
export default function Term({ children, hint }: { children: ReactNode; hint: string }) {
  return (
    <span className="term" tabIndex={0} aria-label={hint}>
      {children}
      <span className="term-marker" aria-hidden="true">
        ⓘ
      </span>
      <span className="term-tip" role="tooltip">
        {hint}
      </span>
    </span>
  );
}
