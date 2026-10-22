# 安装与启动

选择一个长期存放平台的目录。以后不同项目都调用这里的服务，不需要各自安装模型。

## 准备

需要 Windows 11、Git、uv 和可用的 NVIDIA 驱动。当前推理环境为 Python 3.11.16、PyTorch / torchaudio 2.8.0 cu128，主要在 RTX 4090 上验证。CUDA 运行库随 PyTorch wheel 安装，不要求单独安装同版本的 CUDA Toolkit。其他显卡和 CPU 推理尚未完成同等验证。

FFmpeg 从其官方列出的分发渠道单独安装，并加入 PATH。缺少它会影响编码导出、后处理和高级音频处理。不同 FFmpeg 构建的许可不同，详见 [第三方声明](../THIRD_PARTY_NOTICES.md)。

## 第一次安装

在源码目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1
```

脚本会在 `runtime/python` 安装独立 Python，在 `.venv` 建立环境，再安装锁定的依赖。推理代码放入 `vendor`，模型放入 `models`。安装脚本只从上游下载这些文件，不附送本机已有的运行环境或权重。

模型修订和下载校验信息固定在 `config/model-sources.json`，下载器支持断点续传与哈希校验。要换模型版本，应同时更新来源、许可和校验记录，不能直接替换文件。各模型目录的 `provenance.json` 会保存实际下载记录。

脚本完成后会运行核心测试并启动服务。打开 <http://127.0.0.1:8961/>。初次加载模型需要等待；日常生成和录音处理使用本机文件，安装下载阶段需要联网。

仅安装依赖、不下载模型、不启动服务时：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1 -SkipModels -NoStart
```

这个选项适合检查源码和运行核心测试；没有下载模型时不能执行真实配音。安装脚本不会自动修改用户 PATH 或 Codex 配置。

## 日常启动

双击根目录的 `启动语音平台.cmd`，或运行 `bin\voice.cmd start`。停止用 `停止语音平台.cmd`，健康检查用 `健康检查.cmd`。没有注册系统服务或开机任务。

模型空闲默认 5 分钟后卸载；`voice unload` 可手动释放本平台的模型。不会终止其他软件的 GPU 任务。

## 可选：全局命令与 MCP

需要从其他目录调用时，执行 `scripts/register-global.ps1`。它会将本安装的 `bin` 加入当前用户 PATH，并注册用户级 Codex MCP；执行前备份 PATH 和 Codex 配置，备份保存在 `data/backups`。请不要上传这些备份。

注册后新开终端即可使用 `voice`。Codex 需重启或重新连接才能发现新增 MCP 工具。不使用 Codex 的用户可以跳过这一步，WebUI 和 API 仍可独立运行。

## 配置和远程访问

路径、模型、队列和服务参数集中在 `config/platform.json`。相对模型和数据路径以平台安装目录为基准；CLI 传入的相对输入、导出路径以调用者当前目录为基准。

默认只监听 `127.0.0.1`。远程使用需要显式设置 host、allowed_hosts，并在服务环境中设置 `token_env` 指定的访问令牌；未配置令牌时拒绝远程启动。HTTP 使用 Bearer 鉴权，WebUI 输入令牌后建立会话。公网访问还需自行配置可信 TLS 反向代理。不要把凭据写入源码或提交到仓库。
