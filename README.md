# J1 League Score Prediction App

J1リーグ 2026/27シーズンの試合結果・スコアと最終順位を予測し、Streamlitで確認するためのアプリです。

予測は過去データ、チーム成績、選手スタッツ、フォーメーション、移動距離、Eloなどの特徴量と機械学習モデルに基づく参考情報です。実際の試合結果を保証するものではありません。

## 主な機能

- 今後行われる未消化試合すべての予測結果を表示
- 予測スコア、勝敗確率、スコア候補Top5を表示
- 得点者候補Top5とゴール期待値を表示
- チーム・節による絞り込み
- 試合詳細ページの表示
- 過去予測結果と実際の結果の照合
- 絞り込み条件に連動した精度サマリー
- 10,000回シミュレーションによる最終順位・期待勝点・順位確率の表示
- 予測日時ごとの最終順位予測履歴
- Light/Darkモード対応
- 同意ベースのGoogle Analytics 4利用分析
- GitHub Actionsによる定期データ更新

## アプリの表示データ

Streamlitアプリは主に以下の出力ファイルを読み込みます。

```text
outputs/all_unplayed_predictions.json   # 今後行われる未消化試合すべての予測
outputs/latest_predictions.json         # 次節予測
outputs/past_prediction_results.json    # 現行シーズンの過去予測（Streamlit互換）
outputs/past_prediction_results/        # PWA向けのシーズン別過去予測とシーズン一覧
docs/app/data/past_prediction_results/ # PWA公開用に同期したシーズン別過去予測
outputs/standings_forecast/latest.json  # 最新の最終順位予測
outputs/standings_forecast/history/     # 予測日時ごとの順位予測履歴
outputs/last_updated.txt                # 更新時刻
```

現在の「これからの試合」画面では、`outputs/all_unplayed_predictions.json` を優先して表示します。ファイルがない場合のみ `outputs/latest_predictions.json` にフォールバックします。

## ローカルセットアップ

このプロジェクトは `uv` で管理しています。

```bash
cd /Users/akihirookuyama/Soccer_Score_App
uv venv .venv
source .venv/bin/activate
uv sync
```

`requirements.txt` を使う場合:

```bash
pip install -r requirements.txt
```

## Streamlitアプリの起動

```bash
streamlit run app/streamlit_app.py
```

ブラウザで以下を開きます。

```text
http://localhost:8501
```

スマートフォンで確認する場合は、PCとスマートフォンを同じWi-Fiに接続し、Streamlit起動時に表示される `Network URL` をスマートフォンのブラウザで開きます。

## スマートフォン向けPWA

`docs/app/` には、既存の予測JSONを読み込むインストール可能なスマートフォン向けPWAがあります。

主な機能:

- マイチームの端末内保存
- 今後の試合と過去結果のマイチーム絞り込み
- スマートフォン向け最終順位予測カード
- 試合詳細、勝敗確率、スコア候補、得点者候補
- ホーム画面への追加
- 前回取得データのオフライン表示

ローカル確認:

```bash
python -m http.server 4173 --directory docs
```

ブラウザで以下を開きます。

```text
http://localhost:4173/app/
```

PWAはGitHub上の最新の公開予測JSONを読み込みます。Service Workerとインストール動作は、`localhost`またはHTTPS環境で確認してください。

## Google Analytics 4

公開ページ、PWA、Streamlit版は同じGA4ウェブデータストリームを使用します。初期状態では利用状況データを送信せず、利用者が画面上で許可した後にGoogleタグを読み込みます。

主な計測対象:

- Web版・PWA版の選択
- 各画面の表示
- 試合詳細の表示
- チーム、節、シーズン、順位予測時点の絞り込み
- マイチームの設定・解除
- PWAのテーマ変更とインストール操作

測定ID、イベント一覧、プライバシー方針、クロスドメイン設定は `docs/reports/ga4_usage_analytics_2026_27.md` を参照してください。

## 公開ページとSEO

検索流入用の静的ページとして `docs/index.html` を用意しています。GitHub Pagesでは、リポジトリ設定から `docs/` ディレクトリを公開元にすると、以下のようなURLで公開できます。

```text
https://akiokuyama.github.io/J1League_score_prediction_site/
```

静的ページからは、Streamlit Community Cloudで公開している以下のアプリへ遷移します。

```text
https://j1league-score-prediction.streamlit.app/
```

スマートフォン向けPWAはGitHub Pages上の以下のパスで公開する構成です。

```text
https://akiokuyama.github.io/J1League_score_prediction_site/app/
```

Streamlitアプリ側では、ブラウザタブ用の `page_title` と画面見出しに「J1試合予想」「Jリーグスコア予測」「勝敗予想」「得点者候補」を自然に含めています。

## 検証コマンド

変更後やデプロイ前は、以下を実行します。

```bash
python -m compileall app src scripts
pytest
python scripts/validate_prediction_outputs.py
python scripts/validate_past_prediction_results.py
python scripts/validate_standings_forecast.py
```

モデル指標をローカルで確認する場合:

```bash
python scripts/build_model_metrics.py
```

生成される `outputs/local/model_metrics.json` はローカル確認専用です。GitHub Actionsでは生成せず、コミット対象にも含めません。

## GitHub Actions

データ更新と予測更新はGitHub Actionsで運用します。

### Update Results After Matches

- 実行タイミング: 月曜 07:00 JST
- 目的: 週末試合の結果取得と、過去予測結果の更新
- 主な処理:

```bash
python scripts/update_competition_data.py --competition-key 2026_27_j1 --scope results
python scripts/build_past_prediction_results.py --matches Data/processed/matches_2026_27_j1_clean.csv
python scripts/validate_past_prediction_results.py
```

主な更新対象:

```text
Data/processed/matches_2026_27_j1_clean.csv
Data/processed/update_2026_27_j1_report.json
outputs/past_prediction_results.json
outputs/past_prediction_results/2026_27_j1.json
```

このワークフローでは、予測ファイル本体は更新しません。

### Update Predictions Scheduled

- 実行タイミング: 水曜 07:00 JST
- 目的: 週末前のデータ更新、特徴量作成、予測更新
- 主な処理:

```bash
python scripts/run_competition_pipeline.py \
  --competition-key 2026_27_j1 \
  --history Data/features/training_dataset_with_2026_special_point_in_time.csv \
  --shadow-model-dir Models/reviewed_point_in_time_normal_v1
python scripts/build_past_prediction_results.py --matches Data/processed/matches_2026_27_j1_clean.csv
python scripts/build_standings_forecast.py
python scripts/validate_prediction_outputs.py
python scripts/validate_past_prediction_results.py
python scripts/validate_standings_forecast.py
```

主な更新対象:

```text
Data/processed/
Data/features/
outputs/latest_predictions.json
outputs/latest_predictions.csv
outputs/all_unplayed_predictions.json
outputs/all_unplayed_predictions.csv
outputs/prediction_history/
outputs/standings_forecast/
outputs/past_prediction_results.json
outputs/past_prediction_results/
outputs/last_updated.txt
```

### Manual Prediction Update

GitHubの `Actions` タブから手動実行できます。

用途:

- スクレイピング修正後の再実行
- 試合日程・結果の急な変更への対応
- 定期実行失敗後の再実行
- Streamlit表示データの手動更新

## 主要ディレクトリ

```text
Soccer_Score_App/
├── app/                   # Streamlitアプリ
│   └── utils/             # 表示用フォーマッタ、JSON読み込み
├── Data/                  # 学習・推論用データ
│   ├── processed/         # 整形済み試合日程・順位など
│   ├── features/          # 学習・推論用特徴量
│   ├── raw/               # スクレイピング取得データ
│   └── manual/            # 手動管理データ
├── Models/                # 学習済みモデルと特徴量リスト
├── outputs/               # アプリ表示用の予測結果
│   ├── prediction_history/
│   └── local/             # ローカル確認専用出力
├── scripts/               # パイプライン、検証、運用スクリプト
├── src/                   # データ取得、特徴量作成、推論、評価ロジック
├── tests/                 # 回帰テスト
├── docs/                  # レポート、作業記録、指示書アーカイブ
└── archive/               # 旧Notebook、旧RawData
```

## 2026年特別シーズンの扱い

このプロジェクトでは、現在対象としているJ1百年構想リーグを通常の2026シーズンと区別するため、保存名・識別子に `2026_special` を使用します。

例:

```text
Data/processed/matches_2026_special_clean.csv
Data/features/upcoming_features_2026_special.csv
Data/manual/market_values_2026_special.csv
```

## 再学習時のデータ時点

2026年特別シーズンを再学習に加える場合は、必ず以下を実行します。

```bash
python scripts/rebuild_historical_training_dataset.py
python scripts/build_point_in_time_training_dataset.py \
  --reference-dataset Data/features/training_dataset_2021_2025_point_in_time.csv \
  --strategy snapshot_with_aggregate_estimate
python scripts/retrain_models_no_weather.py \
  --dataset Data/features/training_dataset_with_2026_special_point_in_time.csv \
  --output-dir Models/reviewed_2026_special_v1 \
  --test-season 2026_special \
  --test-start-date 2026-05-01 \
  --model-version reviewed_2026_special_v1
```

再学習用データは試合前スナップショットを優先し、動的特徴量はその時点までの試合結果から再構築します。スナップショットがない過去のxG、AGI、KAGIは集計推定値として出所を記録します。xGは試合平均、AGI/KAGIは指数であり、節数では割りません。実績観客数と収容率は学習・推論から除外します。評価を確認して正式反映する場合だけ、再学習コマンドへ `--activate` を追加します。

現在の本番モデルは、通常J1と2026特別リーグを含む `reviewed_2026_special_v1` です。通常J1のみの `Models/reviewed_point_in_time_normal_v1/` は、新シーズン中の比較用シャドーモデルとして保持します。詳しい判断記録は `docs/reports/season_2026_27_model_preparation.md` を参照してください。

## 予測データの考え方

- `latest_predictions.json` は次節予測です。
- `all_unplayed_predictions.json` は未消化試合すべての予測です。
- Streamlitの一覧画面では `all_unplayed_predictions.json` を表示します。
- `prediction_history/` は過去予測の照合に使います。
- 対戦相手が未定の試合は、対戦カードが確定し、特徴量が作成できる状態になってから予測対象になります。

## 運用メモ

- 定期実行では原則として最新データ取得を試します。
- `--use-cache` はデバッグ、再現確認、外部サイト障害時の手動実行向けです。
- `Models/model_features.pkl` を推論時の特徴量スキーマとして扱います。
- 天候特徴量は現在使用していません。
- 旧Notebookは `archive/notebooks/`、旧RawDataは `archive/legacy_rawdata/` に保存しています。
- 作業指示書は `docs/archive/instructions/`、完了レポートや判断メモは `docs/reports/` に整理しています。
