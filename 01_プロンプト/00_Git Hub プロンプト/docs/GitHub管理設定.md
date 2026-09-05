# GitHub上で別途設定する項目

この文書は設定手順・運用設計です。設定が実行済みであることを意味しません。

## Issues / Labels

`.github/ISSUE_TEMPLATE/` に新規・改善・不具合フォームを同梱。
既存のLabelは削除せず、`config/labels.json` を参考に追加する。ラベルの同期は明示承認後に行う。
必須項目は目的／対象／期待結果／影響範囲／確認方法。機密の実データを公開Issueに貼らない。

## PR

テンプレートで目的、Version、非変更範囲、要件、実テスト、未実施、派生物への影響を確認する。
関連Issueがある場合だけCloses等でリンクする。存在しないIssue番号を入れない。
ManifestはPRを作る前の作業ブランチで同期する。mainで後からCIが自動commitする構成にしない。

## Projects

Project名の例：Prompt Library。
Status：Todo／In Progress／Review／Done。Priority：High／Medium／Low。Component：00〜09／Library。
スコアを入れる場合はAnalyticalとMeasuredを別フィールドにし、未実施を0点や100点にしない。
GitHub上のProject作成・権限・自動化はこのZIPでは変更していない。

## Branch保護

正式ブランチへのPRとCI成功を基本にする。利用可能な保護設定は契約・repoの種類で確認する。
一人運用では自分で承認できない必須レビュー設定を機械的に課さない。
検証器やWorkflowを変更するPRは内容を重点確認する。AIによる自己評価だけで自動mergeしない。

## Release

Suiteの公開タグ例：suite-v2.1.0。Componentの版番号と区別する。
同一repo内の複数Componentで単純なv1.0.0タグを使い回さない。
配布前に `--check` とテストを実行し、Release Notesへ実施範囲・未実施を添える。
