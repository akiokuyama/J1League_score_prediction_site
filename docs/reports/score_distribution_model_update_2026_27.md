# 2026-2027シーズン スコア分布モデル更新記録

ステータス: 本番反映済み
コード確定コミット: `026a618` (`Unify score predictions with calibrated distributions`)
本番モデル版: `score_distribution_2026_27_v1`

関連Google Docs:

- [2026-2027シーズン開始時 改善・改修記録](https://docs.google.com/document/d/1qLpb5xwilLSeTRT7RfH4Ip6hMMYbqswj6Q9kArl8AY0/edit)
- [03_スコア予測モデル作成](https://docs.google.com/document/d/1-9FU_KzUezYbk8OjhHjBFh04PSEO7IuB-wvwSWA-12Y/edit)
- [エンハンス計画](https://docs.google.com/document/d/1wGPqG6-GPWEkREY-E4skgvnnRMS9dqdINludph2a6_4/edit)

## 1. 更新の背景

旧方式では、期待得点モデル、勝敗分類器、得点差モデルを別々に学習し、その出力を後処理で統合して最終スコアを決めていた。このため、表示スコアの勝敗方向と勝敗確率トップが一致しない場合があり、公開予測の多くがホーム勝利に見える問題もあった。

今回の更新では、期待得点から作る1つのスコア確率分布を、予測スコア、勝敗確率、スコア候補Top 5の共通の情報源とした。勝敗分類器と得点差モデルは後方互換性のためモデル成果物として保持するが、公開予測の勝敗確率とスコア決定には使用しない。

## 2. 確定した予測方式

ホームとアウェイの期待得点をそれぞれ \(\lambda_H, \lambda_A\) とする。両チームの得点数を独立なPoisson分布と仮定し、スコア \((h,a)\) の確率を次式で計算する。

\[
P(H=h,A=a)=\frac{e^{-\lambda_H}\lambda_H^h}{h!}\frac{e^{-\lambda_A}\lambda_A^a}{a!}
\]

実装では片側0〜8得点を列挙し、有限グリッド内で確率和が1になるよう正規化する。勝敗確率は個別スコアの確率を次のように合算する。

\[
P(\text{home win})=\sum_{h>a}P(h,a),\quad
P(\text{draw})=\sum_{h=a}P(h,a),\quad
P(\text{away win})=\sum_{h<a}P(h,a)
\]

表示する予測スコアは \(P(h,a)\) が最大の組み合わせ、Top 5は確率の高い順の5組とする。Top 5の各確率はTop 5内で再正規化せず、全スコアに対する絶対確率を表示する。

## 3. 期待得点モデルの比較

比較候補は以下の5種類とした。

- L2 LightGBM回帰
- L2 75% + Poisson LightGBM 25%
- L2 50% + Poisson LightGBM 50%
- L2 25% + Poisson LightGBM 75%
- Poisson LightGBM回帰

2023年、2024年、2025年、2026特別リーグ後半を検証期間とするwalk-forward評価を行った。主要結果は次のとおり。

| 候補 | 勝敗Accuracy | 勝敗Log Loss |
| --- | ---: | ---: |
| L2 | 45.38% | 1.06544 |
| L2 75% + Poisson 25% | 45.56% | 1.06543 |
| L2 50% + Poisson 50% | - | 1.06585 |
| L2 25% + Poisson 75% | - | 1.06671 |
| Poisson | - | 1.06803 |

25%ブレンドとL2のLog Loss差は約0.00001で、実質的な改善とは判断できなかった。選択基準ではLog Loss 0.001以内を同等とみなし、より単純なL2を本番採用した。比較結果の完全な記録は `Models/score_model_selection.json` に保存する。

## 4. 確率校正

温度スケーリングを実装した。未校正確率を \(q_k\)、温度を \(T\) とすると、校正後確率は次式となる。

\[
q'_k=\frac{q_k^{1/T}}{\sum_j q_j^{1/T}}
\]

各検証期間に対する温度は、それ以前のout-of-fold予測だけから推定する。全out-of-fold予測から推定された本番候補の温度は `1.103449` だったが、時系列評価では次のように悪化した。

| 指標 | 未校正 | 時系列校正後 |
| --- | ---: | ---: |
| Log Loss | 1.06544 | 1.06762 |
| Brier Score | 0.64311 | 0.64481 |

このため校正機構は実装・記録するが、現在の本番モデルには適用せず `T=1.0` とした。将来、新シーズンの試合数が蓄積した時点で再評価する。

## 5. 特別リーグ後半での評価

2026年5月1日以降の71試合をホールドアウトとした。

| 指標 | 旧勝敗分類器 | 新スコア分布 |
| --- | ---: | ---: |
| 勝敗Accuracy | 38.03% | 49.30% |
| 勝敗Log Loss | 1.1997 | 1.0478 |

新方式の完全スコア一致率は16.90%だった。旧方式の「補正後スコアの勝敗方向」と、新方式の「勝敗カテゴリ確率トップ」は定義が異なるため、今後は勝敗確率のAccuracy、Log Loss、Brier Scoreを主要指標として扱う。

## 6. UI変更

- 期待得点、予測スコア、勝敗確率、Top 5が同じ分布から算出されることを説明する。
- 勝敗確率トップが45%未満、または上位2カテゴリの差が10ポイント未満なら「拮抗」と表示する。
- 「拮抗（ホーム寄り）」「拮抗（アウェイ寄り）」のように、接戦であることと確率トップの方向を分けて表示する。
- 予測スコアと勝敗確率トップが異なる場合は、単一スコアと勝敗カテゴリ合算の違いを表示する。
- Top 5は全スコアに対する確率と、その5候補の合計確率を表示する。

## 7. 新シーズン予測の分布と注意点

未消化379試合の勝敗確率トップは、ホーム勝利267試合、アウェイ勝利112試合、引き分け0試合だった。このうち236試合は「拮抗」判定であり、ホーム勝利267試合すべてが強いホーム優勢を意味しない。

一方、単一の最有力スコアは引き分け281試合、ホーム勝利93試合、アウェイ勝利5試合となった。これは、例えば1-1が単一セルとして最大でも、複数のホーム勝利セルの合計はホーム勝利カテゴリの方が大きくなり得るためである。

この挙動は確率計算上の矛盾ではないが、表示スコアが1-1へ集中する点は新シーズン実績で監視する。表示用スコアへ勝敗方向の重みを加える変更は、確率分布そのものとは別の意思決定になるため、現時点では採用していない。

## 8. 実装・成果物

- `src/predict/score_distribution.py`: スコア分布と勝敗確率の共通計算
- `src/models/probability_calibration.py`: 温度スケーリング
- `src/models/score_model_selection.py`: walk-forward比較と校正判定
- `src/predict/predict_match.py`: 公開予測経路の統合
- `src/evaluation/metrics.py`: 分布ベース評価指標
- `Models/score_distribution_2026_27_v1/`: 採用モデル一式
- `Models/score_model_selection.json`: 候補比較の完全記録

## 9. 再現手順

```bash
python scripts/retrain_models_no_weather.py \
  --dataset Data/features/training_dataset_with_2026_special_point_in_time.csv \
  --output-dir Models/score_distribution_2026_27_v1 \
  --test-season 2026_special \
  --test-start-date 2026-05-01 \
  --model-version score_distribution_2026_27_v1 \
  --score-model auto \
  --activate

python scripts/run_prediction.py --mode next_section
python scripts/run_prediction.py --mode all_unplayed
python scripts/validate_prediction_outputs.py
```

## 10. 検証結果

- `pytest -q`: 46 passed
- モデル読込・1試合推論スモークテスト: 成功
- 最新10試合の予測JSON検証: 成功
- 未消化379試合の予測JSON検証: 成功
- ローカルの一覧、試合詳細、Top 5表示: 確認済み
