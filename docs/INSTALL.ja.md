[简体中文](INSTALL.md) | [English](INSTALL.en.md) | **日本語** | [한국어](INSTALL.ko.md)

# インストールと起動

[README に戻る](../README.ja.md)

継続して使うインストール先を選んでください。各プロジェクトは、ここにあるサービスとモデルを共有します。

## 必要なもの

- Windows 11、Git、[uv](https://docs.astral.sh/uv/getting-started/installation/)、利用可能な NVIDIA ドライバー。
- 現在の推論環境は Python 3.11.16 と PyTorch / torchaudio 2.8.0 cu128 で、主に RTX 4090 で検証しています。CUDA ランタイムは PyTorch wheel に含まれるため、同じバージョンの CUDA Toolkit を別途入れる必要はありません。他の GPU や CPU 推論は同等の検証を終えていません。
- [FFmpeg 公式サイトに掲載された配布先](https://ffmpeg.org/download.html)からインストールし、PATH に追加してください。形式変換、後処理、高度な音声処理に必要です。ライセンスはビルドにより異なります。[第三者ライセンスの表示](../THIRD_PARTY_NOTICES.md)（中国語）を確認してください。
- ダウンロードにはインターネット接続が必要です。モデルと環境に数 GB、キャッシュに追加の容量を確保してください。

## 初回インストール

ソースのディレクトリで PowerShell を開き、実行します。

~~~powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1
~~~

Python は `runtime/python`、専用環境は `.venv` に作成し、固定された依存関係をインストールします。推論ソースは `vendor/`、モデルは `models/`、ダウンロードキャッシュは `runtime/` に保存します。その後、依存関係の確認とコアテストを行い、サービスを起動します。

[WebUI](http://127.0.0.1:8961/) を開いてください。モデルの初回読み込みには時間がかかります。音声生成と録音処理はローカルで実行します。

モデルの配布元とリビジョンは `config/model-sources.json` に固定されています。ダウンロードは再開とハッシュ検証に対応し、各モデルの `provenance.json` に取得記録を残します。モデルを更新する際は、配布元、ライセンス、検証記録を併せて更新してください。

モデルを取得せず、サービスも起動せずに依存関係だけをインストールする場合：

~~~powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1 -SkipModels -NoStart
~~~

ソースの確認やコアテストに使えます。実際の音声生成にはモデルが必要です。インストーラーはユーザーの PATH や Codex 設定を自動変更しません。

## 日常の操作

ルートの `启动语音平台.cmd`（起動）、`停止语音平台.cmd`（停止）、`健康检查.cmd`（状態確認）を使用するか、インストール先で次のコマンドを実行します。

~~~powershell
bin\voice.cmd start
bin\voice.cmd stop
bin\voice.cmd health
bin\voice.cmd unload
~~~

順に起動、停止、状態確認、モデルのアンロードです。必要な一行だけを実行してください。モデルは標準で 5 分間使用されないとアンロードされます。手動アンロードも本サービスのモデルのみを対象とし、他のアプリの GPU タスクを終了しません。ブラウザーを閉じてもタスクは動作します。Windows サービスや自動起動タスクは登録しません。

## グローバルコマンドと MCP

任意の設定です。次のスクリプトには、動作する Codex CLI（`codex` コマンド）が必要です。

~~~powershell
powershell -ExecutionPolicy Bypass -File .\scripts\register-global.ps1
~~~

このインストールの `bin` をユーザーの PATH に追加し、ユーザー単位の Codex MCP サーバーを登録します。変更前に PATH と既存の Codex 設定を `data/backups/` に保存します。バックアップは公開せず、ローカルに保管してください。

新しいターミナルで `voice` を使用できます。Codex を再起動するか MCP に再接続するとツールを検出できます。グローバル CLI だけが必要なら、このスクリプトを使わず、インストール先の `bin` の絶対パスをユーザー PATH に追加してください。WebUI と API は独立して使用できます。

## 設定とリモートアクセス

パス、モデル、キュー、サービスの設定は `config/platform.json` にあります。モデルとデータの相対パスはインストール先を基準とし、CLI の入力・出力の相対パスは呼び出し元の作業ディレクトリを基準とします。

標準の待受先は `127.0.0.1` です。リモート利用には `host`、`allowed_hosts` を明示し、`token_env` が指定するサービス環境変数にトークンを設定します。トークンがなければリモート起動を拒否します。HTTP は Bearer 認証を使い、WebUI はトークン入力後にセッションを作成します。インターネット経由の利用には、信頼できる TLS リバースプロキシも必要です。認証情報をソースやコミットに含めないでください。

バックアップと復元は[保守ガイド](MAINTENANCE.md)（中国語）を参照してください。
