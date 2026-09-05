# ★仮置き保管庫 → My Library

## 普段の操作

ローカルの `my-library/★仮置き保管庫/` にHTML・画像・Markdown・TXTを保存し、
そのリポジトリを開いているCodexに次の一文を渡します。

> ★仮置き保管庫の未処理資料を、AGENTS.mdに従って整理してください。原本と既存デザインを維持し、必要な閲覧HTML・meta.json・索引を作成して、検証後にPRまで作成してください。機密・判断不能な資料は保留し、マージしないでください。

内容を読んで分類するのはCodex、決められた保存・重複防止・索引生成を行うのはPythonです。
Inboxに保存しただけではCodexは起動しません。GitHub ActionsだけでAI分類は実行しません。
追加のAPIキーを要求するコードや、従量課金APIの自動呼出しは含めていません。

### ローカルとCloudの違い

ローカルのCodexは、その作業フォルダに存在する未追跡のInboxファイルを読めます。
Codex Cloudは、PCにあるだけの未pushファイルを読むことはできません。
Cloudを使う場合は、公開して問題ない原本だけを選び、作業ブランチへ明示的に追加します。

```sh
git add -f -- '★仮置き保管庫/公開してよい実ファイル名.html'
```

上記は説明用のパスです。実在する対象ファイルの正確なパスに置き換えます。
`git add -f ★仮置き保管庫` のような一括指定はしないでください。
UI添付を使う場合も、Codexが実際に原本ファイルへアクセスできたことを最初に確認します。
資料をPublicリポジトリへpushすると、PR中でも原本は公開されます。
Pagesに表示しないことと、ファイルを非公開にすることは別です。

## 作られる構成

```text
my-library/
├─ ★仮置き保管庫/              # 入力。原本は削除しない
├─ 22_簿記/                   # 既存のカテゴリをそのまま使用
│  └─ 連番_日本語の資料名/      # folderで指定。idはmeta.jsonで保持
│     ├─ 元の資料.html          # 元HTMLの内容・見た目・相対パスを保持
│     ├─ 元の画像.png
│     └─ meta.json
├─ inbox.config.json
├─ scripts/inbox.py
├─ scripts/inbox_index.py
├─ scripts/build_library.py
├─ scripts/prepare_pages.py
└─ library-all.json            # 自動生成。手編集しない
```

画像・テキストだけの場合は `guide` に指定した「内容名_guide.html」を追加します。
プロンプトの保存先は既存の続きの「連番_日本語名」を `folder` で指定し、
安定した `id` と表示用フォルダ名を分けます。元ファイル名は変更しません。
過去の計画との互換性のため、未指定の場合は従来の `id` フォルダ・`_library_view.html` を使います。
画像は元画像をプレビューとして利用します。サムネイルの新規描画・自動圧縮は行いません。
処理済み原本はscanで `processed` と判定されるため、残っていても同じ資料を増殖させません。
原本を空にしたい場合は、PRのマージ・表示確認後に利用者がローカルで整理します。

## 分類ルール

カテゴリの正本は `library.config.json`。現在の番号を維持します。
`00_マニュアル` / `01_プロンプト` / `11_哲学` / `21_基本情報` /
`22_簿記` / `31_旅行` / `41_AI` / `51_仕事` / `99_その他`。

「プロンプト本体」は主題が哲学や簿記でも通常 `01_プロンプト` を優先し、タグで補足します。
分類が曖昧なだけなら `99_その他`。主題不明、別資料同士か判断不能、機密疑いは保留します。
機密資料を `51_仕事` に入れれば安全になるわけではありません。

## 管理スクリプトの操作

Python 3.10以上、標準ライブラリのみを使います。workflowではPython 3.12を使用します。
Windowsで `python` が使えない場合は、インストール済みPythonランチャーの `py` に読み替えます。

```sh
python scripts/inbox.py scan
python scripts/inbox.py apply .inbox-plan.json
python scripts/inbox.py apply .inbox-plan.json --write
```

2行目はdry-runです。3行目だけが実ファイルを書き込みます。
分類計画 `.inbox-plan.json` はCodexが作る作業用ファイルで、コミットしません。
最上位は `{"version": 1, "items": [...]}`。items内の各資料に以下を指定します。

| キー | 内容 |
|---|---|
| `id` | 安定した資料識別子。既存IDとの重複禁止 |
| `folder` | カテゴリ直下の1階層の保存先。プロンプトは既存の続きの「連番_日本語名」。省略時はid |
| `guide` | 画像・テキスト用の生成HTML名。「内容名_guide.html」を指定。入れ子・入力との衝突は禁止。完成HTMLはentryをそのまま使用 |
| `category` | 設定に存在するカテゴリフォルダ名 |
| `title`, `summary`, `group`, `tags` | 原本を確認して作るタイトル・短い説明・小分類・タグ配列 |
| `type` | guide / study-note / prompt / report 等。省略時reference |
| `files` | 同じ資料の全ファイル。Inbox基準の相対パス配列 |
| `entry` | 主HTMLまたは主テキストの相対パス。画像のみならnullも可能 |
| `sha256` | `{"実際の相対パス": "scanで得た実測SHA-256"}` |
| `publish`, `reviewed` | 公開用途・内容確認済みの場合のみtrue |
| `hold` | trueなら書込み対象外。`reason`に保留理由を記録 |

HTMLと依存画像を同じ資料に含めるとき、元の相対位置を変えずに列挙します。
例として `report.html` が `images/figure.png` を参照する場合、両方のパスをfilesに含めます。
コピー先でも同じ相対位置が保たれます。外部CDNのファイルは自動ダウンロードしません。

### 保存後の必須手順

生成先の資料フォルダを正確なパスで `git add` してから実行します。
既存ビルダーが追跡ファイルだけを索引に載せるため、未ステージの新規HTMLは対象外です。

```sh
python -m unittest discover -s tests -p 'test_*.py' -v
python scripts/build_library.py
python scripts/prepare_pages.py
```

ローカルプレビューは `python -m http.server 8000 --directory _site`。
`file://` でindex.htmlを直接開くのではなく、HTTPサーバー経由で確認します。
出力 `_site` はスクリプト専用です。既存の別用途フォルダは勝手に削除しません。

## 安全装置と限界

SHA-256照合、原本保持、同一入力の二重処理抑制、既存保存先への上書き拒否、
全資料の事前検査、パス逸脱拒否、シンボリックリンク拒否、静的HTML/CSSリンク検査、
索引の実ファイル参照検査、公開出力からのInbox除外を実装しています。

これらはウイルス検査や機密検出の代わりではありません。HTMLのJavaScriptは無害化しません。
JSが動的に組み立てるURL、外部サイト、画像内の個人情報、レイアウトはCodexまたは利用者が別途確認します。
`library-hidden=true` は一覧から隠すだけで、ファイルの非公開化ではありません。

初期対応外は PDF / Office / ZIP / SVG / 動画等です。無理に変換せず保留します。
`<base>`、ローカル絶対パス、UTF-8以外の本文、欠けた依存ファイルも安全に停止します。
必要な場合は原本を残して別コピーを修正し、再scan・再レビューします。
`AGENTS.md` / `AGENTS.override.md` / `meta.json` 等の制御ファイル名の入力も保留対象です。

## 既存の索引と互換性

旧資料はHTMLメタ方式のままです。新Inbox資料のみ `meta.json.ingestion` で識別します。
新資料ではmetaの分類情報を一覧に使用し、`files.guide` の1ページだけを登録します。
そのため補助HTMLの重複登録を避けつつ、元のHTMLを改変せず保存できます。
既存 `library-all.json` を過去の添付で上書きしてはいけません。

## GitHub Pages

初回は Settings → Pages → Build and deployment → Source = GitHub Actions。
PRの検証では公開しません。mainマージ後、生成・索引コミット・デプロイを同じworkflowで行います。
公開ソースは `_site` であり、リポジトリルート全体ではありません。
mainへの直接pushを禁止するルールを後で追加した場合は、botによる索引コミット部分も運用に合わせて変更します。
mainが実行中に進んでpush競合した場合はforce-pushせず、最新mainのworkflowで再実行します。

## 参照した公式仕様（2026-09-05確認）

- Codex AGENTS.md: https://developers.openai.com/codex/guides/agents-md
- GitHub Pages custom workflow: https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages
- Pages公開元とGITHUB_TOKEN: https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site
