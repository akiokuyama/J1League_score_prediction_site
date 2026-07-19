# docs ディレクトリ構成

`docs/` は、現在参照するレポートと過去の作業指示書を分けて管理します。

```text
docs/
├── index.html               # GitHub Pages公開用の検索流入ページ
├── reports/                 # 完了レポート、判断メモ、チェックリスト
│   ├── season_2026_27_model_preparation.md  # 新シーズン開始時の正本
│   ├── week1/
│   ├── week2/
│   ├── week3/
│   ├── week4/
│   ├── week5/
│   ├── week6/
│   └── week7/
└── archive/
    ├── instructions/         # 過去のCodex/Claude指示書
    └── mockups/              # UI確認用モックなど
```

日常的に確認する資料は `docs/reports/` を見ます。作業指示書を見返したい場合は `docs/archive/instructions/` を参照します。

2026-2027シーズン開始時のデータ方針、評価結果、本番／シャドーモデル、再現手順は `docs/reports/season_2026_27_model_preparation.md` を正本とします。
