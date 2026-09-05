# GitHub Library Prompt Suite 2.1.0

更新日：2026年9月5日／Library Contract：2.0／正規フォルダ：**プロンプト一覧/**

00〜08の元の専門機能を保持して改訂し、09の品質監査と開発管理・検証基盤を追加したセットです。
`プロンプト一覧/` は生成用の道具、`content/` は個別資料の正本、`site/` は公開用の派生物です。
GitHubへpushしただけでプロンプトが実行されるわけではありません。Codexへ対象工程を指示してください。

## まず読む

既存リポジトリへ入れる場合は `docs/移行ガイド.md` を先に読み、既存設定・UI・Workflowを差分統合します。
初回のCodex依頼は `docs/Codex初回指示.md` にあります。実行手順は `docs/運用ガイド.md`。

## コンポーネント一覧（スクリプト管理）

<!-- SUITE_COMPONENTS:BEGIN -->

| 番号 | ファイル | Version | 役割 |
|---:|---|---|---|
| 00 | [00_github-library-foundation-builder_master-prompt.md](プロンプト一覧/00_github-library-foundation-builder_master-prompt.md) | 1.1 | 共通基盤を作成・更新・移行する |
| 01 | [01_prompt-architect_master-prompt.md](プロンプト一覧/01_prompt-architect_master-prompt.md) | 1.3 | 再利用するプロンプト原本を設計する |
| 02 | [02_html-guide-generator_master-prompt.md](プロンプト一覧/02_html-guide-generator_master-prompt.md) | 2.1 | 原本を保持してHTML説明書を作る |
| 03 | [03_visual-preview-generator_master-prompt.md](プロンプト一覧/03_visual-preview-generator_master-prompt.md) | 2.4 | 固定デザインでpreviewとthumbnailを作る |
| 04 | [04_meta-json-generator_master-prompt.md](プロンプト一覧/04_meta-json-generator_master-prompt.md) | 2.1 | 個別資料の管理情報と鮮度を管理する |
| 05 | [05_library-json-builder_master-prompt.md](プロンプト一覧/05_library-json-builder_master-prompt.md) | 2.1 | 公開可能資料を決定的に集約する |
| 06 | [06_github-pages-index-generator_master-prompt.md](プロンプト一覧/06_github-pages-index-generator_master-prompt.md) | 2.1 | 安定したindex・404の表示機能を整える |
| 07 | [07_pwa-generator_master-prompt.md](プロンプト一覧/07_pwa-generator_master-prompt.md) | 2.1 | 非破壊でPWA・更新・オフライン機能を加える |
| 08 | [08_github-release-auditor_master-prompt.md](プロンプト一覧/08_github-release-auditor_master-prompt.md) | 2.1 | 公開前・CI・公開後の成果物を監査する |
| 09 | [09_prompt-quality-auditor_master-prompt.md](プロンプト一覧/09_prompt-quality-auditor_master-prompt.md) | 1.0 | プロンプト要件・品質・回帰を監査する |

<!-- SUITE_COMPONENTS:END -->

## 構成

```text
AGENTS.md
プロンプト一覧/          00〜09の完全なMD
config/                 SuiteとLibraryの設定
schemas/                Suite・評価・LibraryのJSON Schema
scripts/                同期・構造検証・評価記録・Libraryビルド
.github/                Issue・PR・CI・任意のPages配布
tests/                 検証器とビルド処理の回帰テスト
evals/                  15件の評価ケースと評価規約
docs/                   運用・移行・要件台帳・外部根拠
reports/                今回の変更差分と検証結果
```

## 最初の確認

Python 3.12以上を実行対象とします。同梱スクリプトは外部のLLM/APIを自動呼出ししません。

```bash
python -m pip install -r requirements-dev.txt
python scripts/build_suite_manifest.py --check
python scripts/validate_suite.py --report-dir reports/local
python -m unittest discover -s tests -v
```

プロンプトや設定を変更した場合は、変更ブランチでCHANGELOGを編集し、以下の順で同期します。

```bash
python scripts/build_suite_manifest.py --write
python scripts/build_suite_manifest.py --check
python scripts/validate_suite.py --report-dir reports/local
```

CI内ではManifestを再生成しません。未同期の変更を失敗として検出します。

## どの工程を使うか

| やりたいこと | 実行する工程 |
|---|---|
| 初回基盤を導入 | 00。既存実装があれば監査して不足だけ補完 |
| 新しい再利用プロンプト | 01 → 09 → 02 → 03任意 → 04 → 05 → 08 |
| 既にある資料を登録 | 02 → 03任意 → 04 → 05 → 08。01は不要 |
| マスタープロンプトの改訂 | 対象MD → 09 → Suite同期・検証 → PR |
| 索引UIを変更 | 06 → 必要に応じ07 → 08 |
| PWA設定を変更 | 07 → 08 |
| 公開後に確認 | 08 POST_DEPLOY |

09は公開後の最後の工程ではなく、プロンプト設計・変更時に使う品質ゲートです。
00・06・07を資料追加のたびに再実行しないでください。

## 安全な初期状態

新規資料は `draft / private / publish=false`。公開条件は `active / public / publish=true` と検証成功です。
ただし、このメタデータはGitHubリポジトリのアクセス制御ではありません。公開repo内の資料はsite外でも閲覧され得ます。
このセットはGitHubへのpush、Projects作成、branch保護設定、Pages有効化、公開を実行していません。
Pages用Workflowは `LIBRARY_PIPELINE_ENABLED=true` でLibrary検証を、`LIBRARY_PAGES_DEPLOY_ENABLED=true` で配布を有効化する設計です。初期状態は配布されません。

## 検証範囲

同梱の `VALIDATION_REPORT.md` と `reports/` は今回のローカル検証記録です。
Suite構造・Pythonツールの実テストと、LLMの実出力比較は別です。独立した実モデルのA/B比較、既存リポジトリの本番動作、Android実機・PWA動作は未実施です。
モデル評価の入力と記録手順は `evals/README.md` を使ってください。

## 版の扱い

Component Versionは各MD冒頭、Suite Versionは `config/suite.config.json`、Library Contractはデータ互換の版です。
旧ファイル名との対応は移行ガイドにあります。履歴はGitとCHANGELOGで管理し、現行フォルダに複数の最新版を並べません。
