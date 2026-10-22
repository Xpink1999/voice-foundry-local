# 自动创建参考与音频修复（0.3）

## 日常操作

「声音设计与音色库」默认进入 **快速创建参考**：上传录音并确认用途授权 → 自动分离、去音乐、降噪和选段 → 试听推荐 → 输入人物名称并保存。无需进入高级处理页面，也无需了解模型参数。建议参考片段 5–30 秒；短于 5 秒会提示，不凭补静音假装达到时长。

完整录音不变。推荐来自原件和各处理结果，清理结果并不天然优于原件；可展开其他候选自行选择。每个参考独立保存，生成一次只使用一个参考，不将多个人物或多个参考简单拼接。选择「保存到已有的人物」可添加场景参考，保留其现有主参考和确认状态。

四个工作区一次只显示一个：

- 快速创建参考：有录音时的默认入口。
- 人物音色库：查找、编辑、试听人物；多个参考的克隆比较放在可选折叠区。
- 声音设计：用文字生成样音，选中后直接创建参考，无需下载再上传。
- 高级音频处理：独立选择去音乐、双人分离、降噪，试听原件与结果；可把任一最终人声输出送入参考选段。

推荐不等于审核通过。保存得到草稿人物，转写也需核对后显式确认；没有试听审核的生成结果仍为 pending。

## 本地开源推理

| 操作 | 权重与固定修订 | 推理代码 | 输出 |
|---|---|---|---|
| 去背景音乐 | [KimberleyJSN/melbandroformer](https://huggingface.co/KimberleyJSN/melbandroformer)，ac9b0614ab3cd7f77219e18ba494dfd93956c348；固定模型卡声明 MIT | [ZFTurbo/Music-Source-Separation-Training](https://github.com/ZFTurbo/Music-Source-Separation-Training)，6fdad13686bb7e84d029ec66f9dbe76e65c93ebf，MIT | 44.1 kHz 双声道人声及背景 |
| 重叠人声分离 | [MossFormer2_SS_16K](https://huggingface.co/alibabasglab/MossFormer2_SS_16K)，407cb030cd66340918ebb6c8cc63b18f8592cdbe，Apache-2.0 | [ClearerVoice-Studio](https://github.com/modelscope/ClearerVoice-Studio)，6b3774dc79c46ae8bed2a4fa5f706f0ac8c75c61，Apache-2.0 | 16 kHz 两路匿名人声 |
| 降噪 | [MossFormer2_SE_48K](https://huggingface.co/alibabasglab/MossFormer2_SE_48K)，eff8c97925c8bec812af707814b3e5d777fd4503，Apache-2.0 | 同上 | 48 kHz 单声道人声 |

权重合计约 1.8 GB，不重复放入项目。模型目录 provenance.json 保存来源、修订、许可声明和文件哈希；runtime/source-provenance.json 保存实际推理源码清单及哈希。许可声明不替代参考人物声音的使用授权。

Windows 无法检出上游训练目录中的 AUX 保留名，因此安装脚本通过固定 Git 对象导出所需推理文件，不修改上游推理实现，不安装训练环境。未使用缺少明确代码许可的备用源码；没有接入存在权重商用限制争议的 Demucs 权重。

## 能力边界

双人分离只输出两路匿名轨道，不能可靠识别真实身份；超过两人、长时间静音、强混响和连续人物交替可能造成串音或身份交换。跨窗口用重叠区匹配两路顺序，无法消除所有漂移。系统保留原录音候选用于比较。去音乐和降噪可能削弱声线、留下残留或引入失真。

长录音采用有界窗口及交叉淡化还原每条连续轨道，保留尾部和长度；这是同一轨道的时间重建，不是把不同参考拼成一个声音。分离后通过混音最小二乘估计恢复各路尺度，避免模型任意幅度被统一放大；只有超过峰值阈值才衰减，增益策略写入输出元数据。处理前后试听可能有音量差异。

最佳推荐是音质、人声比例、长度、ASR 和声纹近似指标形成的建议；不同录音上的听感需人工判断。Hi-Fi 使用当前独立片段与核对后的转写，不从另一片段借用台词。

## 任务、文件与恢复

处理和 TTS 共用 GPU 互斥锁。处理前卸载本平台 TTS，子进程退出后释放显存；其他软件不会被结束。CPU 的 VAD、转写和质量分析独立排队。audio_processing 配置集中在 config/platform.json：设备、CPU 线程、队列限制、超时和窗口长度。

data/recordings 保留原始录音及分析；data/audio-processing/<任务 UUID> 保留处理前 WAV、各步骤及最终输出。每个输出有 UUID、SHA-256、采样率、声道、角色、原件和父任务来源。重复导入同一输出复用录音记录。取消、失败、超时均保留原件；处理中断标记失败，不伪装成功。分析失败可单独重试，复用既有分离结果。

Windows 进度文件可能短暂被读取进程占用。进度写入采用短重试且仅为提示，进度通知失败不再把已经成功的分析变成失败；最终结果文件独立保存。

## 开放调用

所有路由位于 /api/v1，结构以本机 /docs 和 /openapi.json 为准。

- POST /recordings：multipart file、source、authorization、rights_confirmed、smart_reference。HTTP 兼容默认 false，WebUI/CLI/MCP 默认 true。
- GET /recordings/{id}：智能流程状态、原件与派生片段、推荐及子分析状态。
- POST /recordings/from-result：result_id，将设计样音原件直接登记为参考录音。
- GET /audio-processing/capabilities；POST /audio-processing：recording_id、operations、analyze_outputs。
- GET /audio-processing 及 /{id}；POST /{id}/cancel。
- GET /{id}/before 及 /{id}/outputs/{output_id}；POST /{id}/analyze-output：output_id。
- POST /reference-voices：reference_id 加 name 创建草稿人物；或 voice_id、scenario 添加到已有的人物。

```powershell
voice upload-reference .\录音.wav --source "自己的录音" --authorization "拥有配音用途授权" --rights-confirmed
voice process-audio <录音UUID> --operations remove_music separate denoise
voice processing <处理任务UUID>
```

具体 CLI 参数以 voice <命令> --help 为准。MCP 提供 voice_upload_recording、voice_process_recording、voice_audio_processing、voice_create_from_reference；只通过本机 HTTP 调用，任意工作目录共用安装。更新后需重新连接 MCP 才能发现新增工具。
