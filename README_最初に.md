# My Library Inbox更新セット

2026-09-05に `TatsuyaOi/my-library` の実ファイルを確認して作成した更新です。
**GitHubへの書込みは403で拒否され、リモートのブランチ・コミット・PRは作成されていません。**
このセットをローカルまたは書込み可能なCodex環境で適用します。

## 導入

1. ZIPを展開し、`my-library-inbox-update` フォルダを既存my-libraryの直下に置きます。
2. my-libraryを開いたCodexに、同梱の `Codexへの導入指示.md` を渡します。
3. 生成されたPRを確認し、PagesのSourceをGitHub Actionsにしてから自分でマージします。

一括上書きより `apply_update.py` を優先します。既存ファイルが確認時点から変更されていたら停止します。
停止時は無理に進めず、Codexに差分を確認して必要箇所だけ統合させます。

```sh
python my-library-inbox-update/apply_update.py --repo .
# 専用ブランチを用意した後だけ実行
python my-library-inbox-update/apply_update.py --repo . --apply
```

1行目は確認のみ。2行目は書込みです。main/master上の適用は拒否します。
このスクリプト自身はコミット・push・Pages設定変更をしません。
パッケージフォルダは公開資料に含めず、git addしないでください。

既存カテゴリ設定、既存資料のHTML・画像、最新のlibrary-all.jsonは同梱物で上書きしません。
変更対象と確認時のGit blob SHAはmanifest.jsonに記録しています。
実際の全資料を使ったビルド、GitHub Actions実行、Pages公開は適用先のCodex/PRで確認してください。

安全上、Inboxの新規原本は既定でGit追跡対象外です。
ローカルCodexで使うか、Cloudには公開可能な原本だけを明示的に渡してください。
