[简体中文](AUDIO_RESTORATION.md) | [English](AUDIO_RESTORATION.en.md) | **日本語** | [한국어](AUDIO_RESTORATION.ko.md)

# 音声処理とクイック参照

音声ワークスペースには「音声を作成」「音色ライブラリ」「参照クリップ」の三つの入口があります。音声デザインと高度な処理は作成フロー内にあります。画面は [WebUI 操作](WEBUI.ja.md)を参照してください。

## クイック操作

許諾のある録音をアップロード → 話者と発話区間を分析 → 試聴して選択 → 名前を付けて保存 → 人物を作成、または場面別参照を追加 → 配音へ進みます。話者追跡が利用できる場合は人物ごとに区間を整理します。音楽・ノイズ除去は検出結果とインストール済みモデルに応じて使い、録音全体に強制しません。不足するモデルは送信前に表示します。

推奨は 5～30 秒です。短い区間には警告し、無音で長さを合わせません。原本と既存結果を保持し、試聴で比較できます。処理後が常に良いとは限りません。

参照は個別に保存します。短い発話をまとめる場合は、同一人物であることを明示的に確認し、発話時間、重複、最終文字起こしを確認して複合参照として保存します。異なる人物を自動結合しません。場面別参照を追加しても既存の主参照は変わりません。保存後は人物設定へ進むか、参照ライブラリに残せます。

推薦は承認ではありません。文字起こしを確認し、生成結果を試聴して承認してください。詳しくは[操作フロー](WORKFLOW_GUIDE.ja.md)を参照してください。

## ローカルモデル

| 処理 | 固定重み・リビジョン | 推論コード・リビジョン | 出力 |
|---|---|---|---|
| 音楽除去 | [KimberleyJSN/melbandroformer](https://huggingface.co/KimberleyJSN/melbandroformer), ac9b0614ab3cd7f77219e18ba494dfd93956c348, MIT | [ZFTurbo/Music-Source-Separation-Training](https://github.com/ZFTurbo/Music-Source-Separation-Training), 6fdad13686bb7e84d029ec66f9dbe76e65c93ebf, MIT | 44.1 kHz ステレオの声と背景 |
| 重なった声の分離 | [MossFormer2_SS_16K](https://huggingface.co/alibabasglab/MossFormer2_SS_16K), 407cb030cd66340918ebb6c8cc63b18f8592cdbe, Apache-2.0 | [ClearerVoice-Studio](https://github.com/modelscope/ClearerVoice-Studio), 6b3774dc79c46ae8bed2a4fa5f706f0ac8c75c61, Apache-2.0 | 16 kHz、匿名の二人分 |
| ノイズ除去 | [MossFormer2_SE_48K](https://huggingface.co/alibabasglab/MossFormer2_SE_48K), eff8c97925c8bec812af707814b3e5d777fd4503, Apache-2.0 | [ClearerVoice-Studio](https://github.com/modelscope/ClearerVoice-Studio), 6b3774dc79c46ae8bed2a4fa5f706f0ac8c75c61, Apache-2.0 | 48 kHz モノラル音声 |

重みは合計約 1.8 GB で、プロジェクト間で共有します。モデルの `provenance.json` に配布元、リビジョン、ライセンス表示、ハッシュを記録します。`runtime/source-provenance.json` は推論ソースとハッシュです。モデルのライセンスは個人の声の利用許諾ではありません。[第三者ライセンスの表示](../THIRD_PARTY_NOTICES.md)と[資料](../LICENSES/README.md)は中国語です。

上流の学習用パスに Windows の予約名 AUX があるため、インストーラーは固定 Git オブジェクトから推論に必要なファイルを取り出します。推論実装を変更せず、学習環境は入れません。コードの許諾が不明な代替ソースや、商用制限に議論のある Demucs 重みは組み込んでいません。

## 制約と比較

二人分離は匿名の二つのトラックを出し、本人確認はしません。三人以上、長い無音、強い残響、人物の交代では混入やトラックの入れ替わりが起きます。窓の重なりで順番を合わせますが、全ての変動は防げません。原本と比較してください。音楽・ノイズ除去も声質を変え、残留音や歪みを生む場合があります。

長い録音は一定長の窓とクロスフェードで、終端と長さを保った連続トラックに復元します。同じトラックの時間的な再構成であり、異なる参照の結合ではありません。混合音から最小二乗法で各トラックの音量を推定し、任意の増幅を避けます。ピーク閾値を超えた場合だけ減衰し、ゲイン方針を記録します。処理前後で音量差が生じることがあります。

推薦は品質、音声比率、長さ、ASR、近似的な話者指標を組み合わせます。使用する音声は試聴で判断します。Hi-Fi は選んだ単一クリップと対応する修正済み文字起こしを使用し、別クリップの台詞を流用しません。

## タスクと復元

処理と TTS は GPU の排他ロックを共有します。処理前に本サービスの TTS をアンロードし、処理子プロセスの終了で VRAM を解放します。他のアプリは終了しません。CPU の音声検出、文字起こし、品質解析は別キューです。

`config/platform.json` の `audio_processing` にデバイス、CPU スレッド、キュー、制限時間、窓長をまとめています。

`data/recordings` は原本と解析を、`data/audio-processing/<タスク UUID>` は処理前 WAV、中間工程、最終出力を保存します。出力には UUID、SHA-256、サンプルレート、チャンネル、役割、原本と親タスクの出典があります。同じ出力の再取り込みは録音記録を再利用します。

中止・失敗・タイムアウトでも原本を残します。中断した処理は失敗とし、解析だけを既存の分離結果から再試行できます。Windows の進捗ファイルは短時間の再試行で書き込みます。進捗通知の失敗は解析の成功を取り消しません。最終結果は独立して保存します。

## CLI と API

任意のグローバル CLI 登録後に、ID を返された値へ置き換えて必要なコマンドを実行します。権利確認は利用許諾がある場合だけ指定します。

~~~powershell
$recordingId = "RECORDING_ID"
$processingId = "PROCESSING_ID"
voice upload-reference .\recording.wav --source "My recording" --authorization "Permission for this use" --rights-confirmed
voice process-audio $recordingId --operations remove_music separate denoise
voice processing $processingId
~~~

オプションは `voice <command> --help` で確認できます。MCP は `voice_upload_recording`、`voice_process_recording`、`voice_audio_processing`、`voice_create_from_reference` を提供します。更新後は再接続してください。各作業ディレクトリは同じローカル HTTP サービスとモデルを使用します。

ルートは `/api/v1` の下です。スキーマは起動中の `/docs` と `/openapi.json` を参照してください。

| ルート | 用途 |
|---|---|
| POST /recordings | multipart：file、source、authorization、rights_confirmed、smart_reference。既定は HTTP が false、WebUI/CLI/MCP が true。 |
| GET /recordings/{id} | 状態、クリップ、推薦、解析。 |
| POST /recordings/from-result | result_id からデザイン音声を登録。 |
| GET /audio-processing/capabilities | 利用可能な処理。 |
| POST /audio-processing | recording_id、operations、analyze_outputs。 |
| GET /audio-processing or /audio-processing/{id} | タスク一覧・詳細。 |
| POST /audio-processing/{id}/cancel | タスク中止。 |
| GET /audio-processing/{id}/before | 処理前の音声。 |
| GET /audio-processing/{id}/outputs/{output_id} | 出力音声。 |
| POST /audio-processing/{id}/analyze-output | output_id を参照用に解析。 |
| POST /reference-voices | reference_id と name で下書き作成。voice_id と scenario で追加。 |

## 関連ガイド

[README](../README.ja.md) · [インストール](INSTALL.ja.md) · [長文の音声化](LONGFORM.ja.md) · [参照音声](REFERENCE_PREPROCESSING.ja.md) · [保守](MAINTENANCE.ja.md)


[参照整理と音声生成の流れ](WORKFLOW_GUIDE.ja.md)
