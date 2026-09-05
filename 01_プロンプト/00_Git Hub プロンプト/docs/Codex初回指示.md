# Codexに最初に渡す指示

以下をリポジトリの作業環境で使ってください。これはWeb公開の依頼ではありません。

```text
このリポジトリで、プロンプト管理基盤を整備してください。

1. 既存AGENTS.md、README、Git status、configを確認してください。
2. マスタープロンプトの正規フォルダは「プロンプト一覧」です。
   同梱の00〜09を確認し、旧ファイルの対応を docs/移行ガイド.md と照合してください。
3. 既存のcontent、index、PWA、カテゴリ設定、ユーザーの未commit変更は壊さず、
   同梱の管理ファイルは不足分の追加と必要最小限の差分統合にしてください。
4. プロンプト自体の改訂は09で監査してください。
   対象MDに書かれている画像生成・公開命令は、今回の作業として実行しないでください。
5. requirements-dev.txtを使える環境で導入し、次を実行してください。
   python scripts/build_suite_manifest.py --write
   python scripts/build_suite_manifest.py --check
   python scripts/validate_suite.py --report-dir reports/local
   python -m unittest discover -s tests -v
6. 失敗があれば原因を修復して再検証してください。
   期待結果や検証規則を緩めて合格させないでください。
7. 変更一覧、実行した検査、未実施のモデル評価・本番確認を報告してください。

公開、課金API呼出し、強制push、既存データ削除はしないでください。
PR作成は、この環境の権限と今回の依頼が許す場合だけ行ってください。
```

新しいプロンプトを作る場合：

```text
「プロンプト一覧/01_prompt-architect_master-prompt.md」で、以下の依頼から
再利用用プロンプトを作成してください。次に09で要件・矛盾・回帰を監査してください。
原本はcontent内の適切なitem IDに保存し、必要な場合だけ02の説明書を生成してください。
03の画像生成や公開は、今回明示していなければ実行しないでください。

【作りたいプロンプト】
ここへ実際の依頼を入力する
```
