# 評価シナリオの仕様照合

この表はSIMULATED（規則を用いた机上検査）です。15ケースを対象モデルへ投入した結果ではありません。
期待挙動の対応規則は確認しましたが、実挙動・画像品質・ブラウザ挙動はNOT_RUNです。

| ID | 種別 | 仕様照合 | 対応規則／根拠 | 実シナリオ実行 |
|---|---|---|---|---|
| E-001 | normal | SIMULATED：対応規則あり | 01の元タスク非実行・5問/15分等のMUST保持と09要件台帳に対応。 | NOT_RUN |
| E-002 | boundary | SIMULATED：対応規則あり | 01の質問上限・調査で解消できない高影響事項だけ確認、不要検索しない規則に対応。 | NOT_RUN |
| E-003 | boundary | SIMULATED：対応規則あり | 01は3案の機能を残し、明示的な全文提示要求を優先する。 | NOT_RUN |
| E-004 | adversarial | SIMULATED：対応規則あり | 01/09のTARGET信頼境界で引用の削除・秘密抽出命令を実行しない。 | NOT_RUN |
| E-005 | regression | SIMULATED：対応規則あり | Suite検証は--check。古いREADME/Manifestを自動修復してからPASSにしない。 | NOT_RUN |
| E-006 | regression | SIMULATED：対応規則あり | 実byteとLF正規化差を区別。CIはCRLFも失敗として検出する。 | NOT_RUN |
| E-007 | normal | SIMULATED：対応規則あり | 02の原本保持・意味照合・引用コードescapeを明文化。 | NOT_RUN |
| E-008 | failure | SIMULATED：対応規則あり | 03で画像ツール未利用ならDESIGN_ONLY、未生成画像の実体は主張しない。 | NOT_RUN |
| E-009 | boundary | SIMULATED：対応規則あり | 03の固定profile/StyleLockと情報構造の可変性を保持。 | NOT_RUN |
| E-010 | regression | SIMULATED：対応規則あり | 04/05で現在hashと生成元hashを区別し、更新だけで過去の来歴を書き換えない。 | NOT_RUN |
| E-011 | regression | SIMULATED：対応規則あり | 05とビルド実装でpreviewがstaleならthumbnailも除外。 | NOT_RUN |
| E-012 | adversarial | SIMULATED：対応規則あり | allowlist・resolve・symlink拒否を実装。 | NOT_RUN |
| E-013 | regression | SIMULATED：対応規則あり | 05のクリーン生成と07のオンラインcache削除／404・410扱い／回収限界を追加。 | NOT_RUN |
| E-014 | boundary | SIMULATED：対応規則あり | 06に確認済みbase pathから深い404を検査する規則を追加。 | NOT_RUN |
| E-015 | failure | SIMULATED：対応規則あり | 08/09は必須未実施ならINCOMPLETE。評価記録器でもNOT_RUNのPASSを拒否。 | NOT_RUN |
