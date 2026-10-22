# 第三方代码、模型和工具

声场自己的代码和文档使用 Apache-2.0。这个许可不覆盖第三方模型、依赖、商标，也不替用户取得录音、人物声音或书稿的使用权。

公开仓库只提供平台源码、安装脚本和许可资料。安装时，脚本从上游获取运行库、推理代码和模型；这些文件保存在本机，不提交到本仓库。

## 模型与推理代码

| 用途 | 来源与固定版本 | 上游许可 | 随附资料 |
| --- | --- | --- | --- |
| 语音合成 | [OpenBMB/VoxCPM](https://github.com/OpenBMB/VoxCPM) `cce58a5b59303c9bd63d12f23afe6a49a4a80c59`；[VoxCPM2](https://huggingface.co/openbmb/VoxCPM2) `32279effe8c19989596f05d353d1447f51d9e915` | Apache-2.0，模型卡也声明 Apache-2.0 | [代码许可](LICENSES/upstream/VoxCPM/LICENSE)、[模型卡](LICENSES/models/openbmb--VoxCPM2/MODEL_CARD.md) |
| 转写 | [SYSTRAN/faster-whisper](https://github.com/SYSTRAN/faster-whisper) 1.2.1；[small 权重](https://huggingface.co/Systran/faster-whisper-small) `536b0662742c02347bc0e980a01041f333bce120` | MIT | [代码许可](LICENSES/python/faster-whisper/LICENSE)、[模型卡](LICENSES/models/Systran--faster-whisper-small/MODEL_CARD.md) |
| 有效人声检测 | [Silero VAD](https://github.com/snakers4/silero-vad) 6.2.3，ONNX 随上游 Python 包安装 | MIT | [许可目录](LICENSES/python/silero-vad) |
| 背景声音分类 | [AST AudioSet](https://huggingface.co/MIT/ast-finetuned-audioset-10-10-0.4593) `f826b80d28226b62986cc218e5cec390b1096902` | 模型卡声明 BSD-3-Clause；Transformers 推理代码为 Apache-2.0 | [模型卡](LICENSES/models/MIT--ast-finetuned-audioset-10-10-0.4593/MODEL_CARD.md) |
| 说话人特征 | [Resemblyzer](https://github.com/resemble-ai/Resemblyzer) `15d828edebe06bc72b9cabc8ef8ca5ab2cb457ce`，使用仓库自带 pretrained.pt | 仓库为 Apache-2.0，未发现权重另行声明的许可 | [仓库许可](LICENSES/upstream/Resemblyzer/LICENSE) |
| 重叠人声分离 | [MossFormer2_SS_16K](https://huggingface.co/alibabasglab/MossFormer2_SS_16K) `407cb030cd66340918ebb6c8cc63b18f8592cdbe` | 模型卡声明 Apache-2.0 | [模型卡](LICENSES/models/alibabasglab--MossFormer2_SS_16K/MODEL_CARD.md) |
| 降噪 | [MossFormer2_SE_48K](https://huggingface.co/alibabasglab/MossFormer2_SE_48K) `eff8c97925c8bec812af707814b3e5d777fd4503` | 模型卡声明 Apache-2.0 | [模型卡](LICENSES/models/alibabasglab--MossFormer2_SE_48K/MODEL_CARD.md) |
| 分离、降噪的推理代码 | [ClearerVoice-Studio](https://github.com/modelscope/ClearerVoice-Studio) `6b3774dc79c46ae8bed2a4fa5f706f0ac8c75c61` | Apache-2.0；上游文件中的其他署名仍归原作者 | [仓库许可](LICENSES/upstream/ClearerVoice-Studio/LICENSE) |
| 去背景音乐 | [KimberleyJSN/melbandroformer](https://huggingface.co/KimberleyJSN/melbandroformer) `ac9b0614ab3cd7f77219e18ba494dfd93956c348` | 该版本模型卡声明 MIT，见下文 | [原始声明](LICENSES/models/KimberleyJSN--melbandroformer/MODEL_CARD.md) |
| 去音乐的推理代码 | [ZFTurbo/Music-Source-Separation-Training](https://github.com/ZFTurbo/Music-Source-Separation-Training) `6fdad13686bb7e84d029ec66f9dbe76e65c93ebf`，使用 models/bs_roformer | MIT | [代码许可及署名](LICENSES/upstream/Music-Source-Separation-Training/LICENSE) |

下载的文件名、修订和校验信息在 [config/model-sources.json](config/model-sources.json)。安装后，各模型目录的 provenance.json 还会记录实际文件的 SHA-256。下载器不跟随 main 自动升级模型。

### 去音乐模型的许可说明

上游在 [ac9b061 提交](https://huggingface.co/KimberleyJSN/melbandroformer/commit/ac9b0614ab3cd7f77219e18ba494dfd93956c348)中，将模型卡的许可从 GPL-3.0 改为 MIT。本项目固定使用这个版本。该仓库没有单独的 LICENSE 正文，随附的 MODEL_CARD.md 保留了作者的原始声明；本项目没有替作者补写授权，也不对其训练素材的权利作保证。

推理代码来自上表中带有 MIT 正文的 ZFTurbo 仓库。没有使用或分发缺少明确代码许可的备用 Mel-Band-Roformer 源码，也没有安装 Demucs 权重。

## Python 依赖

[完整清单](LICENSES/python-dependencies.json)记录了核查环境中的包名、版本、声明和许可文件哈希；[LICENSES/python](LICENSES/python)保存上游许可正文及发行包附带的第三方声明。它与 requirements.lock.txt 配合使用，不代表其他版本或其他平台的安装包也完全相同。

除 MIT、Apache、BSD、ISC 等许可外，还需要留意以下依赖：

- soxr 使用 LGPL-2.1-or-later；SoundFile 的 BSD 许可不替代底层 libsndfile 的 LGPL 条件。
- certifi 使用 MPL-2.0；tqdm 同时包含 MPL-2.0 和 MIT 部分。
- PyAV 自身的 BSD 许可不替代其 wheel 所带 FFmpeg 库的许可。
- PyTorch 的 BSD 许可不覆盖 CUDA wheel 内所有第三方组件。NVIDIA 运行库有自己的条款。

本仓库不附送这些库的二进制文件。若另行制作整合包、便携包或 Docker 镜像，请针对实际打包进去的文件补做分发检查；不要只复制一份本项目的 Apache 许可证。

## 外部工具

FFmpeg 由用户单独安装，平台通过命令行调用。它的许可取决于具体构建选项：启用 GPL 组件的构建适用 GPL，不能笼统写成 LGPL。本项目开发环境使用过带 `--enable-gpl --enable-version3` 的 Gyan Windows 构建，但仓库和公开源码包都不附送这个程序。请以 [FFmpeg 官方说明](https://ffmpeg.org/legal.html)和所用构建随附的许可为准。

Git、uv、Python、NVIDIA 驱动也由用户从各自官方渠道安装，本仓库不分发其安装程序。模型下载和依赖安装需要联网；正常配音、分析和处理使用本机文件，不上传参考录音。

## 录音和生成内容

请只导入自己有权使用的录音和文本，并保留声音来源与授权记录。把视频中的人声分离出来，或用开源模型克隆声音，都不会自动取得原录音、人物声音、音乐和书稿的权利。测试通过、审核通过，也不等于获得版权或人物授权。

核查日期：2026-10-22。许可原文的来源与哈希见 [LICENSES/source-records.json](LICENSES/source-records.json)。这些记录用于追踪来源，不是对训练数据、输出内容或所有使用场景的法律保证。
