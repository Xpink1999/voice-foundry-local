[简体中文](INSTALL.md) | [English](INSTALL.en.md) | **日本語** | [한국어](INSTALL.ko.md)

# インストールと起動

[README に戻る](../README.ja.md)

継続して使うインストール先を選んでください。各プロジェクトは、ここにあるサービスとモデルを共有します。

## 必要なもの

- Windows 11 x64、[Git](https://git-scm.com/download/win)、[uv](https://docs.astral.sh/uv/getting-started/installation/)、利用可能な NVIDIA ドライバー。
- 現在の推論環境は Python 3.11.16 と PyTorch / torchaudio 2.8.0 cu128 で、主に RTX 4090 で検証しています。CUDA ランタイムは PyTorch wheel に含まれるため、同じバージョンの CUDA Toolkit を別途入れる必要はありません。他の GPU や CPU 推論は同等の検証を終えていません。
- [FFmpeg 公式サイトに掲載された配布先](https://ffmpeg.org/download.html)からインストールし、PATH に追加してください。形式変換、後処理、高度な音声処理に必要です。ライセンスはビルドにより異なります。[第三者ライセンスの表示](../THIRD_PARTY_NOTICES.md)（中国語）を確認してください。
- PyTorch の DLL 読み込みエラーが出る場合は [Microsoft Visual C++ v14 x64 ランタイム](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist)を導入してください。Windows のシステム依存関係であり、このインストーラーは自動変更しません。
- ダウンロードにはインターネット接続が必要です。完全インストールには 30 GiB 以上の空きを推奨します。

## 初回インストール

GitHub で **Code → Download ZIP** を選び、ZIP を「すべて展開」します。`pyproject.toml` と `install-voice.cmd` があるフォルダーを開いてください。ZIP 内から直接実行しないでください。Git でも取得できます。

~~~powershell
git clone https://github.com/Xpink1999/voice-foundry-local.git
cd voice-foundry-local
~~~

Program Files や同期フォルダーを避け、書き込み可能な保存先を選んでください。後から移動する場合は仮想環境の再作成が必要です。管理者権限、既存の Python、CUDA Toolkit、Codex、音色やデータベースは不要です。

`install-voice.cmd` をダブルクリックするか、そのフォルダーで PowerShell を開きます。

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install.ps1
~~~

完全インストールは Python 3.11.16、CUDA 版 PyTorch、固定版の推論ソースと 7 組のモデルを取得し、インポートと CUDA、コアテストを確認して起動します。重みは約 7.1 GiB、PyTorch のダウンロードは約 3.2 GiB です。環境・展開・キャッシュを含め、30 GiB 以上の空きを推奨します。新規環境の音色・プロジェクト・タスクは空です。

[WebUI](http://127.0.0.1:8961/) で一文と声の説明を入力し、生成してください。初回合成ではモデルを読み込むため、画面表示より時間がかかります。結果は試聴と承認が必要です。

CUDA やモデルを取得せず、画面・データベース・基本操作だけを確認する場合：

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install.ps1 -CoreOnly -NoStart
~~~

`-CoreOnly` は Git、NVIDIA GPU、FFmpeg が不要です。空の画面は開けますが、音声生成と録音処理はできません。後でオプションなしで再実行すると完全版になります。`-SkipModels -NoStart` は重みだけを省略し、CUDA 依存関係と推論ソースは取得します。

Python・uv の状態とキャッシュは `runtime/`（モデル用キャッシュは `cache_dir`、標準は `runtime/model-cache`）、専用環境は `.venv`、ソースは `vendor/`、モデルは `models/`、データベースと音声は `data/` に保存します。他のインストール先の環境や録音は読み込まず、ユーザー PATH や Codex 設定も変更しません。

モデルの取得先とリビジョンは `config/model-sources.json` に固定されています。サイズとハッシュを検証し、`provenance.json` を残します。中断したら再実行してください。正常なファイルは再利用します。

## 確認と問題の解決

- ログは `runtime/install.log`、確認結果は `runtime/install-check.json`。失敗時は終了コードが 0 以外になります。原因を直して再実行し、`data/` は保持してください。
- uv / Git が見つからない場合：インストール後、ターミナルを開き直します。ZIP からの完全インストールにも Git が必要です。CoreOnly は不要です。
- 未インストールで起動した場合：起動用ファイルにインストール手順が表示されます。
- 別のインストール先が同じポートを使用している場合：そのサービスを停止するか、このフォルダーの `config/platform.json` の `port` を変えます。ローカルの起動・停止・状態確認はインストール先を照合します。
- CUDA が使えない場合：NVIDIA ドライバーを更新します。CUDA ランタイムは PyTorch に含まれます。[対応バージョンの手順](https://pytorch.org/get-started/previous-versions/)も確認してください。
- FFmpeg がない場合：WAV の文字音声化は可能ですが、録音アップロード、変換、無音カット、音量処理、高度な分離には必要です。導入後ターミナルを開き直すか、設定の `ffmpeg` に実行ファイルの絶対パスを指定します。
- uv のバージョンリンクで権限エラーが出た場合：取得済みの専用 Python を検証し、正常な場合だけ続行します。システム Python は使いません。ダウンロードや検証の失敗時は停止します。

完全インストールの再確認：

~~~powershell
.venv\Scripts\python.exe scripts\check_install.py --profile inference --models
~~~

CoreOnly は `--profile core` を使います。画面表示、依存関係の確認、実際の音声生成は別々に検証します。

## 日常の操作

ルートの `start-voice.cmd`（起動）、`stop-voice.cmd`（停止）、`check-health.cmd`（状態確認）を使用するか、インストール先で次のコマンドを実行します。

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

バックアップと復元は[保守ガイド](MAINTENANCE.ja.md)を参照してください。
