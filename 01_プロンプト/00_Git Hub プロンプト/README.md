# GitHub Library Prompt Suite v2

**作成日：2026年8月24日**  
**Library Contract Version：2.0**

このフォルダは、Markdown原本、HTML説明書、任意のプレビュー画像、`meta.json` を資料単位で管理し、`library.json`、`index.html`、PWAを介してAndroidスマートフォンから閲覧するためのマスタープロンプト一式です。

## 収録ファイル

| 順番 | ファイル | 役割 |
|---:|---|---|
| 0 | `00_github-library-foundation-builder_master-prompt_v1.0.md` | config、Schema、スクリプト、GitHub Actionsを一度作る |
| 1 | `01_prompt-architect_master-prompt_v1.2.md` | 再利用するプロンプト原本を作る |
| 2 | `02_html-guide-generator_master-prompt_v2.0.md` | Markdown原本を保持してHTML説明書を作る |
| 3 | `03_visual-preview-generator_master-prompt_v2.2.md` | 任意のpreviewとthumbnailを作る |
| 4 | `04_meta-json-generator_master-prompt_v2.0.md` | 個別資料のmetaを作る・移行する |
| 5 | `05_library-json-builder_master-prompt_v2.0.md` | 公開可能資料だけをlibraryへ集約する |
| 6 | `06_github-pages-index-generator_master-prompt_v2.0.md` | Android向けindexと404を作る |
| 7 | `07_pwa-generator_master-prompt_v2.0.md` | ホーム画面起動・offline・更新を追加する |
| 8 | `08_github-release-auditor_master-prompt_v2.0.md` | 公開前、CI、公開後を監査する |

## 元ファイルからの対応

| 元ファイル | 修正版 |
|---|---|
| `Master Prompt_v1.1(4).md` | `01_prompt-architect_master-prompt_v1.2.md` |
| `260823_HTML生成プロンプト_視覚表現自動配分版(6).md` | `02_html-guide-generator_master-prompt_v2.0.md` |
| `まとめ画像 1個生成(3).md` | `03_visual-preview-generator_master-prompt_v2.2.md` |
| `json生成(2).md` | `04_meta-json-generator_master-prompt_v2.0.md` |
| `library-Json 生成(1).md` | `05_library-json-builder_master-prompt_v2.0.md` |
| `Github index生成(1).md` | `06_github-pages-index-generator_master-prompt_v2.0.md` |
| `PWA生成.md` | `07_pwa-generator_master-prompt_v2.0.md` |
| `Github 公開前監査(1).md` | `08_github-release-auditor_master-prompt_v2.0.md` |

## 初回の推奨順序

```text
0. Foundation Builderを実行
   ↓
library.config.json / JSON Schema / build scripts / GitHub Actions
   ↓
1. Prompt Architectで原本MDを作る
   ↓
2. HTML Guide Generatorで説明書を作る
   ↓
3. 必要な資料だけpreviewを作る
   ↓
4. meta.jsonを作る
   ↓
5. library.jsonを再構築
   ↓
6. index.html / 404.htmlを作る
   ↓
7. PWA化
   ↓
8. 公開前監査 → deploy → POST_DEPLOY監査
```

## 資料を1件追加するとき

```text
原本MD
↓
HTML説明書
↓
preview（任意）
↓
meta.json
↓
library.jsonを再ビルド
```

`index.html` は `library.json` を読む固定テンプレートなので、資料を追加するたびに再生成する必要はありません。indexのデザイン、機能、data contractを変更するときだけ更新します。

## 推奨フォルダ

```text
content/
└─ example-item/
   ├─ example-item_prompt.md
   ├─ example-item_guide.html
   ├─ example-item_preview.webp
   ├─ example-item_thumb.webp
   └─ meta.json
```

previewとthumbnailは任意です。

## 公開条件

新規metaは安全側で始めます。

```json
{
  "status": "draft",
  "visibility": "private",
  "publish": false
}
```

通常の公開条件：

```text
status = active
visibility = public
publish = true
```

非公開にしたい資料を、indexから隠すだけで保護したことにしないでください。公開ディレクトリと `library.json` へコピーしないことが重要です。

## 更新時の再生成範囲

| 変更 | 再生成・更新 |
|---|---|
| 原本MD | HTML、preview、meta、library |
| summary / tags | meta、library |
| previewだけ | preview情報、meta、library |
| 新資料追加 | その資料一式、library |
| indexデザイン | index、PWA build ID、監査 |
| PWA設定 | manifest、service worker、監査 |
| category体系 | config、全meta監査、library、index |

## stale判定

原本が変わると、以前のHTMLや画像は古くなる可能性があります。

```text
current source SHA-256
≠ guide generated-from source SHA-256
→ guideはstale
```

staleなguideやpreviewは公開索引から一時的に省略し、再生成後に戻す設計です。

## 旧版からの主な変更

- 正しいHTML生成プロンプトを基礎に、原本保持モードを追加
- `meta.json` / `library.json` をSchema 2.0へ更新
- `publish` / `visibility` / `status` を明確化
- sourceと派生物のSHA-256を追加
- previewからthumbnailを派生
- indexを固定テンプレート化し、404を追加
- PWA manifestのid/lang/maskableと更新戦略を強化
- CI / POST_DEPLOY / Git履歴監査を追加
- config / Schema / scripts / GitHub Actionsを作るFoundation Builderを追加

## 注意

各プロンプトは、利用できないツール、未実施のhash、未生成ファイル、未確認の公開設定を「実施済み」と書かないように設計されています。実行環境に応じて未確認事項が残る場合は、公開前監査で明示してください。
