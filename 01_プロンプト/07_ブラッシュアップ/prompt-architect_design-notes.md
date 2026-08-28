# Prompt Architect 実行設計メモ

**実行日：2026年8月28日**  
**対象Version：1.2**  
**処理モード：AUDIT**

## 設計診断

添付資料は、すでに「統合最終版」「短縮版」「カスタマイズ」「使い方」を備えた再利用可能な正式プロンプトです。今回の依頼は内容改善ではなく、GitHub Library Prompt Suite 00〜08を対象資料へ適用するものです。したがって、本文改訂やVersion繰り上げは行わず、既存の安定ID・Version・ファイル名・原文を保持します。

## 3つの処理候補

| 候補 | 方針 | 長所 | 主なリスク | 評価 |
|---|---|---|---|---:|
| A：原本完全保持 | 正式ファイルをバイト単位で保持し、派生物だけ生成 | 既存運用・Version・hashを壊さない | 標準命名 `{id}_prompt.md` と一致しない | 96 |
| B：標準名へ複製 | `prompt-architect_prompt.md` を別途作る | 標準構造へ合わせやすい | 原本が二重化し、正本が曖昧になる | 71 |
| C：Version 1.3へ改善 | 現行内容を再設計して改訂 | 将来改善の余地を取り込める | ユーザー未指定の本文変更になる | 58 |

## 採用

**候補A：原本完全保持**を採用します。主成果物は既存の `01_prompt-architect_master-prompt_v1.2.md` そのもので、GitHub Library内の安定item IDは `prompt-architect` とします。

## 変更しないもの

- 原本文面
- Version 1.2
- 2026年8月24日という原本日付
- 正式ファイル名
- 公開状態（新規metaは draft / private / publish=false）

## 派生工程へ渡す情報

- type: `prompt`
- category: `prompts`
- item ID / slug: `prompt-architect`
- HTMLは原本保持モードで生成
- previewは内容理解用のVisual Wiki／フロー型
