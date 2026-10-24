**简体中文** | [English](INSTALL.en.md) | [日本語](INSTALL.ja.md) | [한국어](INSTALL.ko.md)

# 安装与启动

首次打开可先看[WebUI 操作说明](WEBUI.md)，了解新版导航、生成、审核和导出。

[返回 README](../README.md)

选择一个长期存放平台的目录。不同项目共用这里的服务和模型。

## 准备

- Windows 11 x64、[Git](https://git-scm.com/download/win)、[uv](https://docs.astral.sh/uv/getting-started/installation/) 和可用的 NVIDIA 驱动。
- 当前推理环境为 Python 3.11.16、PyTorch / torchaudio 2.8.0 cu128，主要在 RTX 4090 上验证。CUDA 运行库随 PyTorch wheel 安装，不要求另装同版本 CUDA Toolkit。其他显卡和 CPU 推理尚未完成同等验证。
- 从 [FFmpeg 官方列出的分发渠道](https://ffmpeg.org/download.html)安装 FFmpeg，并加入 PATH。缺少它会影响格式转换、后处理和高级音频处理。不同构建的许可可能不同，见 [第三方声明](../THIRD_PARTY_NOTICES.md)。
- 若出现 PyTorch DLL 加载错误，安装 [Microsoft Visual C++ v14 x64 运行库](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist)。它是 Windows 系统依赖；平台安装脚本不会自动安装或修改它。
- 安装下载需要联网。完整安装建议预留至少 30 GiB。

## 第一次安装

在 GitHub 仓库首页选择 **Code → Download ZIP**，右键 ZIP 选择“全部解压”。进入解压后含 `pyproject.toml` 和 `install-voice.cmd` 的文件夹；不要在压缩包内直接运行。也可以用 Git：

~~~powershell
git clone https://github.com/Xpink1999/voice-foundry-local.git
cd voice-foundry-local
~~~

将文件夹放在长期保留、当前账户可写的位置，避免 Program Files 和同步盘。安装后不要直接移动目录，虚拟环境中的路径需要重新建立。无需管理员权限、预装 Python、CUDA Toolkit、Codex 或已有音色和数据库。

双击 `install-voice.cmd`，或在这个文件夹打开 PowerShell：

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install.ps1
~~~

完整安装会下载 Python 3.11.16、CUDA 版 PyTorch、固定版本推理源码及 7 组模型，检查导入和 CUDA、运行核心测试，再启动服务。模型权重约 7.1 GiB，PyTorch 下载约 3.2 GiB；环境、解包和缓存还需空间，建议至少预留 30 GiB。新安装的音色、项目和任务列表为空。

打开 [WebUI](http://127.0.0.1:8961/)，输入一句文本，在“声音与演绎描述”填写声音要求并生成。首次配音会加载模型，耗时长于打开网页。结果仍待人工试听审核。

只检查界面、数据库和核心流程，不下载 CUDA 或模型：

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install.ps1 -CoreOnly -NoStart
~~~

`-CoreOnly` 不要求 Git、NVIDIA 显卡或 FFmpeg，可启动空白界面，但不能配音或处理录音。之后不带参数重跑即可补全。`-SkipModels -NoStart` 则仍安装 CUDA 依赖和推理源码，只跳过权重；它不是轻量安装。

安装检查会运行核心测试。录音解码、转换和分离相关测试需要 FFmpeg；找不到时会明确显示为跳过，不会把已装好的 CoreOnly 环境判为失败。服务、队列和原采样率 WAV 草稿导出仍会检查；这不代表已验证模型推理或音频处理。

Python、uv 状态和缓存放在 `runtime/`；模型与运行库缓存由 `cache_dir` 指定，默认 `runtime/model-cache`，专用环境在 `.venv`。源码放 `vendor/`，模型放 `models/`，数据库和资产放 `data/`。不读取其他安装的录音、数据库或环境，不自动更改用户 PATH 或 Codex 设置。

模型来源和修订在 `config/model-sources.json`；下载器校验文件大小和哈希，保留 `provenance.json`。下载中断可重跑安装命令，已有有效文件会保留。

## 安装检查与常见问题

- 安装日志：`runtime/install.log`。检查结果：`runtime/install-check.json`。失败会返回非零退出码；修复报错后重跑即可，不要删除 `data/`。
- 找不到 uv 或 Git：先安装对应工具，再重新打开终端。ZIP 下载也需要 Git 来取得完整推理源码；CoreOnly 不需要。
- 未安装就点启动：启动器会显示安装命令，不再只提示找不到 Python。
- 端口已由另一份安装占用：停止那份服务，或修改本目录 `config/platform.json` 的 `port`，随后重试并打开新端口。启动、停止和健康检查均会核对本地安装位置。
- CUDA 不可用：更新 NVIDIA 驱动后重试。PyTorch 自带 CUDA 运行库；不要用安装 Toolkit 代替驱动检查。参考 [PyTorch 对应版本说明](https://pytorch.org/get-started/previous-versions/)。
- 缺少 FFmpeg：WAV 文字配音可用；上传录音、编码导出、裁剪、响度处理和高级分离需要 FFmpeg。安装后重开终端，或在配置的 `ffmpeg` 中填写可执行文件完整路径。
- uv 版本链接权限错误：脚本会检查已经下载的项目内解释器，校验通过才继续，不会改用系统 Python。下载或解释器校验失败时仍停止。

重新检查完整安装：

~~~powershell
.venv\Scripts\python.exe scripts\check_install.py --profile inference --models
~~~

CoreOnly 使用 `--profile core`。网页能打开、依赖检查通过和真实配音成功是不同检查，不能互相替代。

## 日常操作

双击根目录的 `start-voice.cmd`、`stop-voice.cmd` 或 `check-health.cmd`，也可以在安装目录使用以下命令：

~~~powershell
bin\voice.cmd start
bin\voice.cmd stop
bin\voice.cmd health
bin\voice.cmd unload
~~~

四行分别用于启动、停止、检查状态和卸载模型，按需单独执行。模型默认空闲 30 秒后卸载；手动卸载只释放本平台的模型，不终止其他软件的 GPU 任务。关闭网页不会停止后台任务。安装不注册系统服务或开机启动任务。

## 全局命令与 MCP

这一步可选。以下脚本需要已安装且可运行的 Codex CLI（`codex` 命令）：

~~~powershell
powershell -ExecutionPolicy Bypass -File .\scripts\register-global.ps1
~~~

脚本将本安装的 `bin` 加入当前用户 PATH，并注册用户级 Codex MCP。修改前会备份 PATH 和现有 Codex 配置到 `data/backups/`；这些备份只保留在本机。

注册后新开终端可使用 `voice`。重启 Codex 或重新连接 MCP 后可发现工具。如果只需要全局 CLI，可自行将本安装的 `bin` 完整路径加入用户 PATH，不必执行此脚本。WebUI 和 API 可独立使用。

## 配置与远程访问

`VOICE_PLATFORM_CONFIG` 或 `VOICE_PLATFORM_URL` 为空时使用本目录配置和本机地址，不会把空值当成文件路径或远程服务。需要连接另一服务时再填写完整 URL。

路径、模型、队列和服务参数在 `config/platform.json`。相对模型、数据路径以安装目录为基准；CLI 的相对输入、导出路径以调用者当前目录为基准。

默认只监听 `127.0.0.1`。远程访问需显式配置 `host`、`allowed_hosts`，并在服务环境中设置 `token_env` 指定的令牌；缺少令牌时拒绝远程启动。HTTP 使用 Bearer 鉴权，WebUI 输入令牌后建立会话。公网访问还需可信的 TLS 反向代理。不要把凭据写入源码或提交到仓库。

备份、恢复和维护见 [维护说明](MAINTENANCE.md)。
