# 毎日の復習（実装・検証段階）

ルートの「毎日の復習」または公開サイト配下の `app/` から開く。
5分（最大8問）・10分（最大15問）・期限到来分の全問、5形式、4段階自己評価、★、履歴、JSONバックアップに対応する。
日付は日本時間。端末間同期・オフライン対応・記述のAI採点は行わない。

## 現在の対象と制約

`review.config.json` の明示登録教材だけを対象とする。初期対象は基本情報の総合復習ノートとスパッタ圧力の2件。
簿記Boost ReaderはJavaScript内に本文があり、画像だけの資料には抽出可能な本文がないため未登録。
教材内のスクリプトを実行して抽出しない。新規教材も公開確認後、この設定へ固定lesson_idと公開パスを追加する。
改名時は同じlesson_idのパスを更新する。コピーは必ず別ID。曖昧な自動改名判定は行わない。

AIの実行方法・認証・利用上限が未設定のため、初回2教材の問題生成はblocked。
模擬問題はテスト内だけにあり、公開データには含まない。
実AI品質・公開URL・Android実機での確認は未完了。画面だけでV1完成とはしない。

## ローカル操作

```sh
python -m unittest discover -s tests -p 'test_*.py' -v
node tests/review-core.test.mjs
python scripts/build.py --preview
python scripts/review.py --generate
python scripts/prepare_pages.py
python -m http.server 8000 --bind 127.0.0.1 --directory _site
```

`http://127.0.0.1:8000/app/` を開く。`--lesson fe-general` は指定教材の差分処理、`--all` は強制再生成。
通常は意味内容に差分がなければAIを呼ばない。失敗後も正常な教材は再利用し、失敗分だけ再試行する。
既存の原本・Inbox資料の出力ハッシュには触れない。

## AI実行契約

実行サービスは未選定。承認されたプロバイダへの接続アダプターを用意してから有効にする。
`REVIEW_AI_COMMAND` は実行コマンドのJSON配列（例：`["python", "path/to/approved_adapter.py"]`）。
シェル文字列は受け付けない。標準入力でJSONを1件受け、標準出力にJSONを1件返す。
認証情報は環境変数／GitHub Secretsへ設定し、コマンド引数・教材・Git・ログに含めない。

入力 `operation: generate` には教材・根拠・既存問題・ID台帳・変更章・保持対象が入る。
返却形式は `{"questions":[...]}`。問題項目は `scripts/review.py` のPOLICYとvalidate_reviewに定義。
`operation: validate` は別呼び出しで候補と原文を検証し、
`{"results":[{"question_id":"...","pass":true,"reason":"根拠のある理由"}]}` を返す。
全active問題を個別に評価し、全件合格した候補だけを採用する。同じモデルでも別処理が必要。
アダプターは入力の教材命令を実行せず、外部検索や教材外の知識補完を許可しない。

設定済みコマンドがない場合はblockedとなる。既定は並列数1、1教材3試行まで、1実行12呼出しまで、
1呼出し120秒・入力10万文字まで。費用の通貨上限・トークン上限・モデル選択は接続先側にも設定する。
この実装は呼出し回数の上限を設けるが、課金額を保証しない。アダプターを用意せず自動生成の成功とはしない。

## データと更新

`review/bundle.json` は教材状態と永続ID台帳、教材別の不変JSONへの参照を持つ。
問題本体は `review/data/<lesson_id>-<hash>.json`。候補を全体検証し、参照マニフェストを原子的に置換する。
公開時は教材別 `review/<lesson_id>.json` と `review/library.json` に展開し、台帳・過去版はPagesへ出さない。
既存のlibrary-all.json・カテゴリlibrary.jsonは従来の生成元を維持する。

本文変更後の失敗では旧版を保存し、staleとして通常出題から外す。削除・公開解除では通常出題から除外し、
公開解除された教材の問題本文もPagesへ出さない。端末の過去履歴は削除しない。
原文引用は該当アンカーの抽出本文に存在することを確認する。曖昧な問題の最終品質はAI評価と実教材確認が必要。

`manual_override: true` の既存問題は自動変更・削除しない。元根拠との不一致はstaleとして保留する。
手動修正は台帳のanswer_hash・revisionと整合させ、必ず再生成／独立品質検証を通す。
review/dataの過去版を直接書き換えず、新しい候補として扱う。

Markdown教材のanchors.jsonは既存の公開アンカーを固定する対応表。
見出し改名時は対応表のキーも同じIDを保って更新する。新見出しは内容由来のIDで既存の連番をずらさない。
HTML教材は既存アンカーを使用し、アンカーがない場合は自動改変せず保留する。

## GitHub Actions

PRではテスト・公開対象検査のみ。AI呼び出しはmain上だけ。
登録済み教材のHTML、Markdown原本・meta.json・anchors.jsonの差分を検出する。
README・CSS・review・libraryだけの変更はAI生成を起動しない。
対象を新規登録したら手動実行でlesson_idを指定する。手動全件実行も可能。

Repository Variablesの `REVIEW_AI_COMMAND` に承認済み実行コマンドを設定する。
`REVIEW_AI_MODEL` / `REVIEW_AI_ENDPOINT` とSecret `REVIEW_AI_API_KEY` はアダプターへ渡すための予約環境変数。
サービス選定前は設定不要。リポジトリ変数へ秘密情報を置かない。
生成とデプロイは既存workflow内で直列に実行し、反映前に最新mainと開始HEADの一致を確認する。
新しいcommitが先行していれば停止し、新しい実行に任せる。保護ブランチを迂回しない。
マージはユーザー。GitHub側の権限・設定・実AI経路は別途実環境で検証する。

## 履歴と復元

IndexedDBの評価イベント・問題状態・セッション進行を同一トランザクションで保存する。
同一出題IDの重複を拒否し、別タブでも同じセッションを再開する。保存失敗時は次へ進まない。
バックアップはイベント・★・設定を含む。復元前に件数を表示し、確認後に非破壊マージする。
同一IDの異なるイベントや未対応版は取り込まず、既存DBを保持する。廃止問題の履歴も残す。
未評価の入力は復習完了に数えず、端末内セッションにのみ保存する。

## ブラウザテスト

`tests/review-browser.mjs` はPlaywrightがある環境で実行する。
必要なら `PLAYWRIGHT_MODULE` に利用可能なPlaywrightモジュールの絶対パスを設定する。
実サイトのビルドを上記ローカルサーバーで配信してから `node tests/review-browser.mjs`。
`REVIEW_TEST_URL` でテスト用ローカルURLを指定可能。テストは新規ブラウザコンテキストを使い、
5形式の模擬JSONをネットワーク差し替えで供給する。実ユーザーの履歴・公開問題は変更しない。
模擬AI／ブラウザ試験の成功は実AI・Android実機の成功を意味しない。
