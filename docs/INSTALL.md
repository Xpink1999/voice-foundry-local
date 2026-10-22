**简体中文** | [English](INSTALL.en.md) | [日本語](INSTALL.ja.md) | [한국어](INSTALL.ko.md)

# 安装与启动

[返回 README](../README.md)

选择一个长期存放平台的目录。不同项目共用这里的服务和模型。

## 准备

- Windows 11、Git、[uv](https://docs.astral.sh/uv/getting-started/installation/) 和可用的 NVIDIA 驱动。
- 当前推理环境为 Python 3.11.16、PyTorch / torchaudio 2.8.0 cu128，主要在 RTX 4090 上验证。CUDA 运行库随 PyTorch wheel 安装，不要求另装同版本 CUDA Toolkit。其他显卡和 CPU 推理尚未完成同等验证。
- 从 [FFmpeg 官方列出的分发渠道](https://ffmpeg.org/download.html)安装 FFmpeg，并加入 PATH。缺少它会影响格式转换、后处理和高级音频处理。不同构建的许可可能不同，见 [第三方声明](../THIRD_PARTY_NOTICES.md)。
- 安装下载需要联网。模型与运行环境需要数 GB 磁盘，下载缓存还需额外空间。

## 第一次安装

在源码目录打开 PowerShell，运行：

~~~powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1
~~~

脚本将 Python 安装到 `runtime/python`，在 `.venv` 建立环境，安装锁定的依赖。推理源码放在 `vendor/`，模型放在 `models/`，下载缓存放在 `runtime/`。随后检查依赖、运行核心测试并启动服务。

打开 [WebUI](http://127.0.0.1:8961/)。首次加载模型需要等待。后续配音和录音处理在本机完成。

模型来源和修订固定在 `config/model-sources.json`，下载器支持断点续传与哈希校验，各模型目录的 `provenance.json` 记录下载信息。更新模型时需同步来源、许可和校验记录。

只安装依赖、跳过模型下载且不启动服务：

~~~powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1 -SkipModels -NoStart
~~~

这适合检查源码和运行核心测试；没有模型时不能实际配音。安装脚本不会自动修改用户 PATH 或 Codex 配置。

## 日常操作

双击根目录的 `启动语音平台.cmd`、`停止语音平台.cmd` 或 `健康检查.cmd`，也可以在安装目录使用以下命令：

~~~powershell
bin\voice.cmd start
bin\voice.cmd stop
bin\voice.cmd health
bin\voice.cmd unload
~~~

四行分别用于启动、停止、检查状态和卸载模型，按需单独执行。模型默认空闲 5 分钟后卸载；手动卸载只释放本平台的模型，不终止其他软件的 GPU 任务。关闭网页不会停止后台任务。安装不注册系统服务或开机启动任务。

## 全局命令与 MCP

这一步可选。以下脚本需要已安装且可运行的 Codex CLI（`codex` 命令）：

~~~powershell
powershell -ExecutionPolicy Bypass -File .\scripts\register-global.ps1
~~~

脚本将本安装的 `bin` 加入当前用户 PATH，并注册用户级 Codex MCP。修改前会备份 PATH 和现有 Codex 配置到 `data/backups/`；这些备份只保留在本机。

注册后新开终端可使用 `voice`。重启 Codex 或重新连接 MCP 后可发现工具。如果只需要全局 CLI，可自行将本安装的 `bin` 完整路径加入用户 PATH，不必执行此脚本。WebUI 和 API 可独立使用。

## 配置与远程访问

路径、模型、队列和服务参数在 `config/platform.json`。相对模型、数据路径以安装目录为基准；CLI 的相对输入、导出路径以调用者当前目录为基准。

默认只监听 `127.0.0.1`。远程访问需显式配置 `host`、`allowed_hosts`，并在服务环境中设置 `token_env` 指定的令牌；缺少令牌时拒绝远程启动。HTTP 使用 Bearer 鉴权，WebUI 输入令牌后建立会话。公网访问还需可信的 TLS 反向代理。不要把凭据写入源码或提交到仓库。

备份、恢复和维护见 [维护说明](MAINTENANCE.md)。
