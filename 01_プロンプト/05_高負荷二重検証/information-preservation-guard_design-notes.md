# information-preservation-guard 設計メモ

## Prompt Architect判定

- **動作モード:** `AUDIT + PORT + TEMPLATE`
- **タスク分類:** 出力制御／情報保持／長文・ファイル処理／二重検証／エージェント品質保証
- **推奨対象AI:** 汎用LLMおよびCodex等のコーディングエージェント
- **安定item ID:** `information-preservation-guard`
- **Version:** `1.1`（入力の正式Versionを維持）
- **主成果物:** `information-preservation-guard_prompt.md`

## 採用判断

入力一式には、Lean・Precision・Adaptiveの比較、統合最終版、追加モジュール、単体検証モジュール、既存の二重検証レポートがすでに存在します。新しい内容を付け足してVersionを変更するのではなく、実運用用の既存「統合最終版 v1.1」を主成果物として**内容を1 byteも変更せず**Library命名へ移植しました。

## 原本整合

- 入力ファイルSHA-256: `f7254df2726aef9f82415ab9bf36bba94a3d054635be659aa2ef09c6c5735a5b`
- 主成果物SHA-256: `f7254df2726aef9f82415ab9bf36bba94a3d054635be659aa2ef09c6c5735a5b`
- byte一致: `True`
- Section見出し数（`##`）: `46`
- Section 0〜26: `True`

## 変更しなかったもの

- 本文
- Version 1.1
- 2026年8月26日改訂の表記
- Section 0〜26
- 入力欄のテンプレート構造
- SOURCE / RESEARCH / GENERAL / INFERENCE / PROPOSAL / UNKNOWNの分類
- 最大5回の修復サイクルと二重検証条件
