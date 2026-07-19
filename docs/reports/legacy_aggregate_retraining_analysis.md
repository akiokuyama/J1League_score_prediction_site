# 特別シーズン再学習：旧集計値方式の調査記録

> この資料は調査過程の記録である。最終判断は [`season_2026_27_model_preparation.md`](season_2026_27_model_preparation.md) を参照すること。

## 訂正した事項

旧ノートブックと生成済み学習CSVを調べた結果、Football Labの値の単位解釈に誤りがあることを確認した。

- Football Labの期待値（xG）は、シーズン合計ではなく1試合当たりの値である。
- AGI / KAGIは指数であり、シーズン合計ではない。
- したがって、これらを38節で割る処理は採用しない。
- 旧学習CSVですでに分割されていた値は、各シーズンの最大節数倍して公開単位へ戻した。
- 市場価値はEUR百万単位、チームスタッツのシーズン合計は試合平均へ正規化した。

## 調査から残した方針

過去シーズンと特別リーグには完全な節別スナップショットがない。このため、動的特徴量は試合前の結果だけから再構築し、xG / AGI / KAGIは取得可能な集計推定値として割り当て、出所を別CSVへ記録する。

旧方式をそのまま再現した比較用データと候補モデルは採用対象ではない。標準の採用データは次のファイルである。

- `Data/features/training_dataset_2021_2025_point_in_time.csv`
- `Data/features/training_dataset_2026_special_point_in_time.csv`
- `Data/features/training_dataset_with_2026_special_point_in_time.csv`
