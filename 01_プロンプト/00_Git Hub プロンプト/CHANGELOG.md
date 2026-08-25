# CHANGELOG

## 2026-08-24 — Library Contract 2.0

### Added

- 共通基盤生成プロンプト
- `library.config.json` 契約
- `meta.schema.json` / `library.schema.json`
- 明示的公開制御
- slug / aliases
- source / guide / preview / thumbnail hash
- provenance
- previewから派生するthumbnail
- deterministic build ID
- `404.html`
- CI / POST_DEPLOY / ROLLBACK_CHECK
- Markdown + JSON監査レポート

### Changed

- Prompt Architect 1.1 → 1.2
  - 統合最終版を主MDとして実生成
  - 設計メモを分離
- HTML Generator → HTML Guide Generator 2.0
  - 原本がある場合は原本を保持しHTMLだけ生成
  - 新規時のみMD+HTML同時生成
- Visual Preview Generator 2.1 → 2.2
  - WebP優先、thumbnail、alt、成果物manifest
- Meta Generator → Schema 2.0
- Library Builder → Schema 2.0・公開フィルタ・鮮度判定
- Index Generator → Schema 2.0・固定テンプレート・404
- PWA Generator 1.0 → 2.0
  - manifest id/lang/dir/purpose
  - navigation/indexのNetwork First
  - build IDと更新通知
- Auditor 1.0 → 2.0
  - config/Schema、公開漏えい、hash、Git履歴、公開後監査

### Safety

- 新規資料の初期状態を `draft / private / publish=false` に変更
- staleな派生物を公開索引から除外
- private資料が公開成果物へ混入した場合をBLOCKER扱い
