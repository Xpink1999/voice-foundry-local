# 参考录音预处理与多参考人物

版本 0.2.0。入口为 WebUI「声音设计与音色库」，也可使用 API、CLI 或 MCP。分析与生成全程在本机完成，音频不会发往第三方服务。

## 操作流程

1. 上传有授权的音频并填写来源。浏览器预读时长；服务器保留上传原件与 SHA-256，另行解码为 16 kHz 单声道分析副本。可上传长录音，单份限制 200 MB、0.5–1800 秒。
2. 独立 CPU 队列执行人声检测、近似声线分组、音乐/噪声分类和转写。推荐独立参考为 5–30 秒，默认候选最长约 20 秒，最多 24 个，优先保留较长的有效候选。原录音可随时试听和下载。
3. 按声线临时标签 S1/S2 筛选、逐段试听、勾选保存。每个文件来自原录音的一段连续时间区间；小停顿保留，长静音及声线变化切开，不将不相邻区间拼接。未经选择的候选不会进入可用参考库。
4. 自动转写可编辑，保留版本历史。只有用户实际校对才勾选确认。Hi-Fi 可使用未确认转写生成预览，但元数据始终保留草稿标记。
5. 创建人物，选择主参考并勾选其他参考，可填写场景标签。生成时默认使用主参考，也可单次切换场景参考。绝不把多个参考串接给模型。
6. 比较同一人物至少两个已保存片段：同文本、默认种子 42/84 分别克隆。按参考声线相似度、跨种子一致性、ASR 字符误差和源质量给出可查看的排名。点击「应用推荐」才创建人物新草稿版本；其他参考和场景标签保留。人物在比较期间被修改时拒绝应用，防止覆盖新编辑。

对比样音及 Hi-Fi 结果仍为待审核。自动评分与应用建议不等于用户试听认可，也不会把结果改成正式资产。

VoxCPM2 的 Hi-Fi 沿用片段演绎，禁用额外声音描述，并保留人物原有描述供 reference 模式使用。实际验证发现，续接模式把描述接在 prompt_text 后可能朗读描述；平台因此按能力声明拒绝 Hi-Fi 的显式 style，并在元数据记录默认描述被忽略的原因。需要额外情绪、语速提示时切换参考克隆模式，效果仍属近似引导。

## 模型与边界

| 功能 | 本地实现 / 开源来源 | 许可与边界 |
|---|---|---|
| 人声起止 | [Silero VAD](https://github.com/snakers4/silero-vad)，silero-vad 6.2.3、ONNX | MIT；会有音乐等误检，保留低人声置信度提示 |
| 自动转写 | [Faster-Whisper](https://github.com/SYSTRAN/faster-whisper) 1.2.1 + [small 权重](https://huggingface.co/Systran/faster-whisper-small) | MIT；CPU int8，多语言，短片段/噪声可能幻听，需校对 |
| 音乐/噪声提示 | [AST AudioSet](https://huggingface.co/MIT/ast-finetuned-audioset-10-10-0.4593) | BSD-3-Clause；整录音按 10 秒窗口，候选再单独检测，sigmoid 模型分数不是校准概率 |
| 声线分组/比较 | [Resemblyzer](https://github.com/resemble-ai/Resemblyzer) 说话人嵌入 + 本地余弦聚类 | Apache-2.0；VAD 人声按至少 1 秒、最大 2.5 秒窗口估计，S1 等仅本次录音内匿名标签 |
| 静音、片段文件、排名 | 平台独立实现 | 静音按 20 ms RMS、-50 dBFS；不是语义识别；评分公式公开在 reference_analysis.py |

多人检测依据按顺序出现的声线变化；不是身份鉴定。情绪、短语、语言变化可能被分为多类，也可能混淆相似人物。0.3 已接入双人重叠分离、去背景音乐与降噪，默认快速入口会自动串联处理并保留原件候选，见[自动创建参考与音频修复](AUDIO_RESTORATION.md)。两路输出为匿名声线，不是可靠身份鉴定；仍可能串音、残留和失真，未检出也不保证干净。

自动推荐采用 `0.45 × 参考余弦相似 + 0.25 × (1 − 截断后的字符误差) + 0.20 × 跨种子余弦相似 + 0.10 × 源质量`。短台词 ASR 波动较大，非中文语音、特殊口音和领域词可能影响排序。它只帮助缩小试听范围，不是通用声纹鉴定或客观质量认证。

字符比较先统一标点、大小写、全半角和繁简字，避免 Whisper 的繁体输出被误判为念错。繁简转换使用 [OpenCC Python](https://github.com/yichen0831/opencc-python) 0.1.7，Apache-2.0；原文与原始转写保持不变。

## 存储、安装与维护

- 原件：`data/recordings/<UUID>/original.<原格式>`；每次尝试有独立 `analysis-*` 目录、请求、进度、日志和结果。失败及取消保留原件，重试生成新尝试目录。
- 当前候选 WAV 使用 16 kHz 单声道分析采样，原录音采样与原字节不变；需要保留原始带宽作为参考时可使用 CLI `upload-reference --direct` 上传 0.5–90 秒的已裁剪音频。Hi-Fi 是模型克隆模式名称，不表示自动改善录音带宽。
- 已保存参考：SQLite references 实体指向独立 WAV，含源录音 UUID/时间区间、SHA-256、来源授权、转写历史、质量和固定模型来源。音色保存参考集合的版本快照；生成结果再冻结实际使用的单个参考。
- 统一权重：`models/faster-whisper-small`、`models/AST-AudioSet`、`models/Resemblyzer`；每个目录 `provenance.json` 保存修订、许可和逐文件 SHA-256。Resemblyzer 源码在 `vendor/Resemblyzer`，固定提交；Silero ONNX 随私有环境安装包提供。
- 新安装运行 `scripts/install.ps1`，由 `scripts/download_reference_models.py` 下载固定修订。依赖加入 `requirements-inference.txt` 与实际安装锁定文件，全部位于平台 `.venv`，不影响项目环境。
- 配置集中在 `config/platform.json` 的 `reference_preprocessing`，包括模型目录、CPU 线程、队列上限、超时、片段长度、声线相似阈值及检测阈值。修改需重启服务，先备份配置与数据库。
- 分析任务各启一个 CPU 子进程，完成即退出；不占用 CUDA 显存，TTS 继续由单独 GPU 队列限流。停止服务会停止当前分析子进程；重新启动后中断任务标失败，可重试。

## CLI / MCP

```powershell
voice upload-reference .\访谈.wav --source "本人录音" --authorization "已获得指定用途授权" --rights-confirmed
voice recordings
voice recording <录音UUID>
voice generate --text "故事从这里开始。" --voice-id <人物UUID> --reference-id <片段UUID> --clone-mode hifi --wait
```

`upload-reference` 默认执行自动预处理，返回录音任务 UUID；`--direct` 保留旧的短参考直接上传路径。CLI 保存片段、比较等暂通过 REST 或 MCP 调用。

MCP 新增 `voice_upload_recording`、`voice_recording`、`voice_save_reference_clips`、`voice_compare_references`、`voice_reference_comparison`；生成支持单次 reference_id/clone_mode，音色保存支持 reference_ids/reference_scenarios。全局服务及模型跨目录共用，启动新的 MCP 客户端可发现新工具。应用主参考建议及审核在 WebUI 明确操作。

## 验证

核心测试使用临时数据库和测试引擎，真实模型验证需要单独执行。公开版不附带历史录音或运行截图；验证方法见 [测试说明](TESTING.md)。
