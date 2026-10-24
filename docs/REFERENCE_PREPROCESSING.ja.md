[简体中文](REFERENCE_PREPROCESSING.md) | [English](REFERENCE_PREPROCESSING.en.md) | **日本語** | [한국어](REFERENCE_PREPROCESSING.ko.md)

# 参照音声の準備

「制作 → 音声デザイン・音色ライブラリ → 参照を作成」を開きます。ライブラリ、文字からの音声デザイン、音声処理は別タブです。生成画面の音色管理からライブラリへ移動し、選んだ音色を生成に引き継げます。[WebUI 操作](WEBUI.ja.md)に画面と手順を掲載しています。

録音の解析と生成はローカルで実行します。音声を第三者のサービスへ送信しません。

## 操作の流れ

1. 利用許可のある録音をアップロードし、出典と許諾内容を入力します。ブラウザーで長さを確認し、サーバーは原本と SHA-256 を保存して、16 kHz モノラルの解析用コピーを作ります。上限は 1 件 200 MB、長さは 0.5～1,800 秒です。
2. 独立した CPU キューで音声区間検出、近似的な話者グループ分け、音楽・ノイズ分類、文字起こしを行います。推奨参照は 5～30 秒です。標準の候補は最大約 20 秒、最大 24 件で、長めの有効区間を優先します。原本は試聴・ダウンロードできます。
3. S1/S2 など録音内の仮ラベルで絞り、試聴して保存するクリップを選びます。各クリップは連続する一つの時間区間です。短い間は残し、長い無音や声の変化で分割します。離れた区間は結合せず、未選択の候補は参照ライブラリに入りません。
4. 自動文字起こしを修正できます。版の履歴を残し、実際に確認した後だけ確認済みにします。未確認の文字起こしでも Hi-Fi の試聴生成は可能ですが、メタデータは下書きのままです。
5. 音色を作り、主参照と、場面ラベル付きの追加参照を選びます。生成時には主参照か選択した一つだけを使い、複数参照を連結しません。
6. 同じ人物の保存済み参照を二つ以上比較できます。同じ文章を標準シード 42/84 で生成し、参照との類似度、シード間の安定性、ASR 文字誤り率、原音の品質で順位を示します。推薦の適用は明示操作で、音色の新しい下書き版を作ります。他の参照と場面ラベルは残ります。比較中に音色が変更された場合は古い推薦の適用を拒否します。

比較用音声と Hi-Fi 結果も審査待ちです。スコアや推薦は承認を代行しません。

Hi-Fi は参照の話し方を引き継ぎ、追加のスタイル説明を使いません。音色の説明は reference 方式用に保持します。`prompt_text` に説明を足すと読み上げる可能性があるため、Hi-Fi の明示的な `style` は拒否します。既定の説明を無視した理由はメタデータに記録します。感情や速度を追加指定する場合は reference 方式を使いますが、制御は近似的です。

## 解析ツール

| 機能 | ローカル実装・配布元 | ライセンスと制約 |
|---|---|---|
| 音声区間 | [Silero VAD](https://github.com/snakers4/silero-vad) 6.2.3, ONNX | MIT. 音楽などを誤検出する場合があります。 |
| 文字起こし | [Faster-Whisper](https://github.com/SYSTRAN/faster-whisper) 1.2.1 + [small](https://huggingface.co/Systran/faster-whisper-small) | MIT. CPU int8、多言語。短い区間やノイズで誤った文章を出す場合があります。 |
| 音楽・ノイズの検出 | [AST AudioSet](https://huggingface.co/MIT/ast-finetuned-audioset-10-10-0.4593) | BSD-3-Clause. 10 秒窓と候補単位で確認。sigmoid スコアは校正済み確率ではありません。 |
| 話者グループ分け | [Resemblyzer](https://github.com/resemble-ai/Resemblyzer) | Apache-2.0. コサイン距離で分類。1～2.5 秒の音声窓を使用し、S1 は録音内だけのラベルです。 |
| 無音・切り出し・順位 | Voice Foundry | 20 ms RMS、−50 dBFS で無音を検出。意味解析ではありません。式は reference_analysis.py。 |

話者分けは順番に現れる声の変化に基づき、本人確認ではありません。感情、発話、言語の変化で一人が複数群になったり、似た声を混同したりします。クイック操作では二人の重なった声の分離、音楽除去、ノイズ除去も行い、原本候補を比較用に残します。[音声処理](AUDIO_RESTORATION.ja.md)を参照してください。出力は匿名トラックで、他の声の混入、残留音、歪みが生じることがあります。警告がなくても音質を保証しません。

参照比較のスコア：

`0.45 × 参照とのコサイン類似度 + 0.25 × (1 − 上限処理した文字誤り率) + 0.20 × シード間コサイン類似度 + 0.10 × 原音の品質`

短い台詞では ASR が不安定です。中国語以外、アクセント、専門語も順位に影響します。試聴候補を絞るための指標で、汎用的な声紋判定や品質認証ではありません。

文字比較では句読点、大文字・小文字、全角・半角、簡体字・繁体字を統一します。変換には [OpenCC Python](https://github.com/yichen0831/opencc-python) 0.1.7（Apache-2.0）を使用し、原文と元の文字起こしは変えません。

## 保存と設定

原本は `data/recordings/<UUID>/original.<拡張子>` に保存します。試行ごとに `analysis-*` フォルダーと要求、進捗、ログ、結果を作ります。失敗・中止でも原本を残し、再試行は別フォルダーに保存します。

候補 WAV は現在 16 kHz モノラルの解析用コピーを使います。原本のバイトとサンプルは変えません。切り出し済み参照の帯域を保持する場合は、0.5～90 秒の音声を `upload-reference --direct` で渡してください。Hi-Fi はクローン方式の名称で、帯域の自動復元ではありません。

保存済みの `references` は独立 WAV を参照し、録音 UUID・時間範囲、SHA-256、許諾、文字起こし履歴、品質、固定モデルの出典を保持します。音色の版は参照集合を保存し、生成結果は実際に使った一つの参照を固定します。

共有モデルは `models/faster-whisper-small`、`models/AST-AudioSet`、`models/Resemblyzer` にあります。`provenance.json` はリビジョン、ライセンス、ファイルのハッシュを記録します。Resemblyzer ソースは `vendor/Resemblyzer` の固定コミット、Silero ONNX は専用環境のパッケージに含まれます。インストーラーは `scripts/download_reference_models.py` で固定モデルを取得し、依存関係はプラットフォームの `.venv` に入ります。

`config/platform.json` の `reference_preprocessing` でモデル先、CPU スレッド、キュー、制限時間、クリップ長、話者・検出閾値を設定します。変更前に設定と DB をバックアップし、変更後は再起動してください。

解析は CPU 子プロセスで、完了後に終了し CUDA VRAM を使いません。TTS は別の GPU キューです。音声処理ガイドの分離・クリーンアップ工程は GPU を使用します。サービス停止で解析も停止し、再起動後は中断した解析を失敗として再試行できます。

## CLI と MCP

任意のグローバル CLI 登録後に使用します。ID は返された値に置き換え、必要なコマンドを実行してください。権利確認は実際の許諾がある場合だけ指定します。

~~~powershell
$voiceId = "VOICE_ID"
$referenceId = "REFERENCE_ID"
$recordingId = "RECORDING_ID"
voice upload-reference .\recording.wav --source "My recording" --authorization "Permission for this use" --rights-confirmed
voice recordings
voice recording $recordingId
voice generate --text "This is a voice sample." --voice-id $voiceId --reference-id $referenceId --clone-mode hifi --wait
~~~

`upload-reference` は標準で自動処理し、録音タスク ID を返します。`--analyze-only` は解析のみ、`--direct` は用意済みの短い参照を直接登録します。クリップ保存と比較は WebUI、REST、MCP を使用します。

MCP は `voice_upload_recording`、`voice_recording`、`voice_save_reference_clips`、`voice_compare_references`、`voice_reference_comparison` を提供します。生成は `reference_id` と `clone_mode`、音色は `reference_ids` と `reference_scenarios` に対応します。更新後は再接続し、推薦の適用と承認は WebUI で明示的に行います。

## 検証範囲

コアテストは一時 DB とテストエンジンを使います。実モデルの検証は別に行います。公開版に過去の録音やスクリーンショットは含めません。[検証範囲](TESTING.md)は中国語です。

## 関連ガイド

[README](../README.ja.md) · [インストール](INSTALL.ja.md) · [長文の音声化](LONGFORM.ja.md) · [音声処理](AUDIO_RESTORATION.ja.md) · [保守](MAINTENANCE.ja.md)
