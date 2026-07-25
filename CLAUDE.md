# このリポジトリで作業するときの約束

## マージ

**GitHub のマージボタン／`gh pr merge` を使わない。** どちらも GitHub 側でマージコミットが
生成され、著者名がアカウントの表示名になるため、履歴の著者表記が不揃いになる。
ローカルでマージして push すること（push すれば PR は自動で MERGED になる）。

```bash
git checkout main
git merge --no-ff <branch> -m "Merge pull request #<N> from ops324/<branch>"
git push origin main
```

## Git LFS

`frontend/public/data/*.json`（合計約26MB）は LFS 管理。**クローン直後に `git lfs install`**
を実行すること。未導入だと実体ではなくポインタが取得され、静的サイトのビルドが壊れる。

`git push` が LFS の実体を上げないことがある（pre-push フックが無いクローンで起きる）。
push 後は `git lfs push --all origin <branch>` を明示的に叩き、**別ディレクトリへクローンし直して
実体が取得できるか**で確認する。ポインタのまま push しても push 自体は成功してしまう。

## 焼き固めJSONを更新したとき

分析ロジックや golden snapshot を変えたら `make static` で焼き直す。忘れると CI の
`static-export` ジョブが落ちる（`export_static --check` が時刻・pk を除外した意味的比較で照合）。

## 誠実性フレームワーク

本プロジェクトは「主張できること／できないこと」を厳密に切り分け、機械で強制することを
核に置いている（`docs/SPEC.md` §5）。**ρ=0.903（道路長との順位相関）や片側 p=0.962
（中核仮説が支持されなかったこと）といった不利な実測値を、弱めたり削ったりしないこと。**
新しい指標を出すときも同じ基準で限界を併記する。
