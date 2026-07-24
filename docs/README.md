# docs ディレクトリ構成

`docs/` は、現在参照するレポートと過去の作業指示書を分けて管理します。

```text
docs/
├── index.html               # GitHub Pages公開用の検索流入ページ
├── reports/                 # 完了レポート、判断メモ、チェックリスト
│   ├── season_2026_27_model_preparation.md  # 新シーズン開始時の正本
│   ├── score_distribution_model_update_2026_27.md  # スコア分布・校正・モデル比較の確定記録
│   ├── final_standings_forecast_2026_27.md  # 最終順位予測・UI・週次履歴の実装記録
│   ├── ga4_usage_analytics_2026_27.md  # GA4・同意管理・イベント計測の実装記録
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

期待得点からのスコア分布、L2/Poisson比較、温度スケーリング、UI表示変更の詳細は `docs/reports/score_distribution_model_update_2026_27.md` を参照します。

10,000回シミュレーションによる最終順位予測、履歴保存、日程不足時の扱いは `docs/reports/final_standings_forecast_2026_27.md` を参照します。

Google Analytics 4の測定ID、同意管理、イベント一覧、クロスドメイン測定、確認方法は `docs/reports/ga4_usage_analytics_2026_27.md` を参照します。
