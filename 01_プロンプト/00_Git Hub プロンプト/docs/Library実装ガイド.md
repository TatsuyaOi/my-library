# Library用の同梱実装

## 今回の範囲

共通設定、meta/library Schema、公開allowlistビルド、構造検証、リテラルリンク検査を実装しています。
これは既存サイトの再作成ではありません。現在のindex、PWA、実資料は今回の添付に含まれていないため、既存サイトを変更・確認したとは扱いません。

## ディレクトリ

`content/<id>/` に原本・guide・preview・thumbnail・metaを置きます。
新規構成では承認済みのindex/404/PWA/iconを `site-ui/` に置き、`site/` へビルドします。
既存の構成が違う場合は00で差分統合してください。既存のsiteを削除して移行しないでください。
このstarterは出力を専用 `site/` に限定し、所有マーカーがない既存siteの上書きを拒否します。

```bash
python scripts/build_library.py --dry-run --data-only
python scripts/build_library.py --report reports/local/library-build.json
python scripts/validate_library.py
python scripts/check_links.py --site site
```

1行目は索引計画だけの読取り専用確認。2行目以降は実資料・index・404の導入後に使います。
公開対象0件での上書き、既存公開IDの除去は既定で止めます。意図を確認した操作だけ `--allow-empty`、`--allow-removals` を使います。

## 対応済み

厳格JSON、正式Schema、公開3条件、hash一致、stale依存の連鎖、ID/slug/alias衝突、公開関係IDの射影、パス脱出・symlink拒否、決定的なbyte列、余計な公開ファイル検出。
除外件数や内部警告はprivateレポートに分離し、公開statsの該当項目は0にします。total_itemsと公開カテゴリ件数は実数です。
metaがSchema不適合の場合は、このstarterでは安全側にビルド全体を停止します。元仕様の「除外して継続」より厳しい実装方針です。
contentのフォルダ一括コピーはせず、filesの明示参照だけを公開します。additionalにも秘密情報を入れないでください。

## 別検査が必要なもの

本文の意味の正確さ、機密情報の網羅検査、画像のデコード／日本語文字、動的JavaScript、深い404、Service Worker、Android実機、Git履歴、公開済みURLは08と対象環境で確認します。
内部のsynthetic画像fixtureはhash連鎖検証専用のbyte列です。実画像の描画テストではありません。

## 公開前監査ゲート

配布時は `reports/release/github-audit-report.json` を08で作成してください。
`build_id` が今回の `site/library.json` と一致し、schema／publication／links／content-consistency／browser-uiがEXECUTED・PASSで、証拠ファイルが必要です。
sw.jsがある場合はpwaも必須です。未実施はINCOMPLETEとなり、deployは止まります。

```json
{
  "schema_version": "1.0",
  "mode": "CI",
  "verdict": "INCOMPLETE",
  "build_id": null,
  "counts": {"blocker": 0, "high": 0},
  "checked": [],
  "recommended_exit_code": 2,
  "unverified": ["この例は監査記録の形であり、監査未実施"]
}
```

各checked要素はid、execution、result、evidence_file（repo基準の相対パス）を持たせます。
ファイルがあることだけで実験の真正性は保証できないため、PRで内容も確認します。
公開後の08 POST_DEPLOYは別作業です。CI成功だけで公開確認済みとしません。

## パスと差し替えの補足

公開base pathが確定している場合は `config/library.config.json` の `site.base_path` に `/repo/` などを設定します。未設定のまま推測して補完しません。
リンク検査はこのbase path配下のルート相対URLを許可します。ブラウザでの深い404からの復帰確認は別途必要です。
`files.additional` へguide／preview／thumbnailを重複指定して鮮度検査を迂回することは禁止します。
ビルドはコピー後のhashを再検査し、既存の管理下siteを退避して差し替えます。差し替え失敗時は旧siteを復元します。
