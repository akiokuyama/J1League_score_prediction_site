# GA4利用分析 実装記録（2026/27シーズン）

## 目的

J1試合予測AIの公開ページ、PWA、Streamlit版を同じGA4ウェブデータストリームで計測し、利用者がどの画面・機能を利用しているかを改善判断に使えるようにする。

## GA4構成

| 項目 | 設定 |
|---|---|
| ウェブデータストリーム | J1試合予測AI Web・PWA・Streamlit |
| 測定ID | `G-D757SHS30N` |
| GitHub Pages | `akiokuyama.github.io` |
| Streamlit Community Cloud | `j1league-score-prediction.streamlit.app` |
| データストリーム数 | 1 |

GitHub Pagesの親ページとPWAは `docs/analytics.js` を共有する。Streamlit版は `app/utils/analytics.py` のComponents v2ブリッジを使用する。両方で同じ測定IDと同じイベント名を使う。

## 同意・プライバシー方針

- 初期状態では `analytics_storage` を `denied` にする。
- 利用者が明示的に許可するまで、Googleタグ本体を読み込まない。
- 広告用途の `ad_storage`、`ad_user_data`、`ad_personalization` は常に `denied` にする。
- 選択結果は各サイトのブラウザ内に `j1_analytics_consent_v1` として保存する。
- PWAは設定画面、Streamlitは「利用状況データ」欄、公開ページはプライバシー欄から後で変更できる。
- 氏名、メールアドレス、自由入力内容、正確な位置情報は送信しない。
- マイチーム関連ではクラブ識別コードと操作種別のみを送る。

GitHub PagesとStreamlitはオリジンが異なるため、同意状態はサイトごとに保持する。クロスドメイン測定でユーザー・セッションを連携しても、同意状態をURLパラメータで引き継がない。

## 計測イベント

| イベント | 主な発火箇所 | 主なパラメータ |
|---|---|---|
| `page_view` | Googleタグ初期化 | GA4標準 |
| `select_app_surface` | 親ページのWeb/PWA導線 | `target`, `position` |
| `app_open` | PWA・Streamlit起動 | `app_surface`, `display_mode`, `has_my_team` |
| `view_app_section` | これから・過去・順位・設定 | `section_name` |
| `view_match_detail` | 試合詳細 | `match_id`, `match_status`, チームコード |
| `select_team_filter` | チーム絞り込み | `filter_area`, `team_filter` |
| `select_matchweek_filter` | 節絞り込み | `filter_area`, `matchweek_filter` |
| `select_result_filter` | 過去結果の判定絞り込み | `result_filter` |
| `select_past_season` | 過去結果のシーズン選択 | `season_key` |
| `select_standings_snapshot` | 順位予測時点の選択 | `snapshot_date` |
| `set_my_team` | マイチーム保存 | `team_code` |
| `clear_my_team` | マイチーム解除 | `previous_team_code` |
| `theme_changed` | PWAテーマ変更 | `theme` |
| `install_prompt_available` | インストール可能状態 | なし |
| `install_attempt` | ホーム画面追加操作 | `install_method` |
| `install_prompt_result` | ブラウザ確認結果 | `outcome` |
| `install_instructions_open` | 手動追加手順 | `platform`, `prompt_available` |
| `app_installed` | PWAインストール完了 | `display_mode` |
| `data_load_error` | PWAデータ取得失敗 | `error_area` |

すべての独自イベントに `app_surface` を付け、`pwa` と `streamlit` を比較できるようにする。

## 二重送信防止

PWAでは同一ページ内の初回イベントに一意なキーを付ける。Streamlitでは次の二段階で防止する。

1. Pythonのセッション状態でイベント番号を採番し、送信待ちキューを1回だけ取り出す。
2. ブラウザ側の `Set` に送信済みイベントキーを保存し、Streamlitの再実行で同じイベントが渡っても再送しない。

画面やフィルターは、既に初期化済みの値が実際に変化した場合だけイベントを作る。初期描画でフィルター操作イベントを水増ししない。

## クロスドメイン測定

コードでは両実装で以下のドメインをGoogleタグのlinkerへ設定する。

```text
akiokuyama.github.io
j1league-score-prediction.streamlit.app
```

GA4管理画面でも、対象ウェブデータストリームの「タグ設定を行う」→「ドメインの設定」に同じ2ドメインを「含む」条件で登録する。

## 確認結果

- JavaScript構文チェック：成功
- Python構文チェック：成功
- 同意前にGoogleタグを読み込まないこと：PWA・Streamlitで確認
- 許可後に測定IDのGoogleタグを1回読み込むこと：PWA・Streamlitで確認
- PWA設定画面から送信停止へ変更できること：確認
- 公開ページのプライバシー説明と設定変更UI：確認
- ブラウザのエラー・警告：なし
- 自動テスト：`tests/test_analytics.py` と既存PWA・Streamlitテストで確認

公開後は、GA4のリアルタイムとDebugViewで本番URLからのイベント受信を最終確認する。通常レポートへの反映には時間差があるため、初回確認はリアルタイムを使用する。

## 分析開始後の推奨設定

イベント受信後、GA4の「カスタム定義」で次のイベントスコープのカスタムディメンションを登録すると、探索レポートで比較しやすくなる。

- `app_surface`
- `section_name`
- `filter_area`
- `team_filter`
- `season_key`
- `snapshot_date`
- `display_mode`
- `install_method`
- `outcome`

`match_id` は値の種類が多いため、標準レポートの主要ディメンションにはせず、詳細調査時だけ利用する。

## 継続的な確認方法

### GA4の画面だけで確認する

同じプロパティにQiita用ストリームがあるため、プロパティホームの総数をアプリ利用者数として扱わない。

GA4の「探索」には `J1アプリ 週次利用状況` を作成済み。タブ `イベント別` で、過去28日間のイベント数と総ユーザー数を25件まで表示し、ストリーム名が `J1試合予測AI Web・PWA・Streamlit` と完全一致するデータだけに絞っている。通常の週次確認は、この探索を開いて期間を変更するだけでよい。

1. GA4でプロパティ `489676180` を開く。
2. 「探索」→ `J1アプリ 週次利用状況` → `イベント別` を開く。
3. 必要に応じて期間を「過去7日間」または「過去28日間」に変更する。
4. `app_open`、`view_match_detail`、`set_my_team`、`app_installed`、`data_load_error` のイベント数と総ユーザー数を確認する。
5. ページ、流入元、デバイスまで調べる場合は標準レポートを開き、比較またはフィルタで同じストリーム名を指定する。

週次では次の5点だけを見ればよい。

- `app_open` のユーザー数
- `app_open` のイベント数 ÷ ユーザー数
- `view_match_detail` のユーザー数 ÷ `app_open` のユーザー数
- `set_my_team` のユーザー数 ÷ `app_open` のユーザー数
- `data_load_error` のイベント数

### 1コマンドでレポートを作る

Google Analytics Data APIを一度設定すれば、J1用ストリームだけを集計したMarkdownとJSONを生成できる。

初回のみ:

```bash
python -m pip install -r requirements-analytics.txt
gcloud auth application-default login \
  --scopes="https://www.googleapis.com/auth/cloud-platform,https://www.googleapis.com/auth/analytics.readonly"
```

Google Cloud側でGoogle Analytics Data APIを有効にし、ログインするGoogleアカウントにGA4プロパティの閲覧権限を付与しておく。

毎週の実行:

```bash
python scripts/generate_ga4_usage_report.py --days 28
```

出力先:

```text
outputs/local/analytics/ga4_usage_report_latest.md
outputs/local/analytics/ga4_usage_report_latest.json
```

スクリプトはストリームID `15315638495` を全クエリに適用するため、Qiitaのデータを混ぜない。認証情報はリポジトリへ保存せず、Application Default Credentialsまたはリポジトリ外のサービスアカウント鍵を使用する。

初回の簡易分析は `docs/reports/ga4_usage_analysis_2026-08-08.md` に記録する。
