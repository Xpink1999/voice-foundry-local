# 模块导航与扩展

| 模块 | 职责 |
|---|---|
| config.py | 安装根目录定位、统一配置和远程鉴权启动约束 |
| schemas.py | 版本化 API 输入约束 |
| store.py | SQLite 事务、实体、事件和在线数据库备份 |
| service.py | 音色版本、项目隔离、持久任务、生命周期、审核和导出 |
| engines/base.py | SpeechEngine 协议 |
| engines/voxcpm.py | 唯一依赖 VoxCPM API 的生产适配器 |
| engines/__init__.py | 配置驱动注册表 |
| audio.py | 音频校验、分段、哈希、WAV、FFmpeg、分段 SRT |
| references.py | 原录音、独立参考片段、转写版本、异步预处理及克隆对比编排 |
| reference_worker.py / worker_runner.py | 分析或修复子进程入口、进度与取消、Windows 进度锁容错、退出清理 |
| restoration.py | 独立修复队列、智能推荐编排、原件与派生来源、创建人物 |
| processing_engines.py | 固定模型适配器、窗口重建、分离幅度恢复及模型身份校验 |
| reference_analysis.py | Silero VAD、Whisper 转写、AST 检测、匿名声线聚类及近似对比评分 |
| longform.py | 有界文本导入、章节/分段位置、冻结配置、逐段检查点和恢复 |
| longform_store.py | 作品/章节/分段/尝试/审核/导出独立 SQLite 索引与分页 |
| longform_export.py | 后台块式合成、逐章/整本 WAV/RF64、FFmpeg、ZIP64 和审核保护 |
| assets.py | 14 类资产的引用检查、原子批量软删除、回收站及同批恢复 |
| web/longform-ui.js / longform.css | 长文导入、目录、逐段/连续试听、审核和导出工作区 |
| web/assets-ui.js | 通用管理/回收站、列表删除和批量入口 |
| web/review-export-ui.js | 批量试听审核与同页导出联动 |
| exports.py | 通用、游戏资源、媒体配音的输出目录适配器 |
| api.py/server.py | HTTP、SSE、本机边界、静态界面和服务生命周期 |
| client.py/cli.py | 跨目录客户端与服务启动、显式目标导出 |
| mcp_server.py | 独立 MCP 工具，仅通过 HTTP 使用平台 |
| web/ | 中英日韩静态 WebUI，无外部字体或翻译服务依赖 |
| web/workflow.js | 无 DOM 的批量解析、项目范围校验、编码、地址与选择范围规则 |
| web/workflow-ui.js / workflow.css | 工作位置、同标签草稿、跨工作区衔接、分页、设置保护和删除撤销 |
| web/batch-ui.js | 人物名称匹配、角色分配、提交前预览和批量错误提示 |
| web/i18n.js、locales/、translations.js | 浏览器语言识别、手动切换、草稿恢复及四语言离线词条 |
| scripts/build_i18n.py | 词条完整性与占位符检查，生成浏览器词条包 |
| web/theme.js、themes.css | 系统/浏览器配色监听、手动选择记忆、双配色与真实波形重绘 |
| web/references-ui.js | 生成时的单片段选择和人物多参考编辑 |
| web/voice-workspace.js | 快速创建、人物库、声音设计、独立高级处理及 A/B 试听 |
| web/jobs-ui.js | 当前/归档视图、批量选择、服务端分页及恢复；默认每页 50 项 |
| tests/ | 模型契约、任务/版本/隔离/审核/恢复/导出/边界测试 |

## 增加语音模型

1. 新建适配器，实现 engines/base.py 的协议：capabilities、identity、load、unload、synthesize。
2. 返回 mono float32 PCM 数组迭代器，声明实际采样率。identity 必须返回固定模型 ID、修订及权重来源；不在能力表中冒充未支持的功能。
3. 在 config/platform.json 的 engines 注册 `模块路径:类名`，依赖仅装在平台环境；其他软件仍通过 REST 调用。
4. WebUI 从 /models 读取选项；不支持的流式/设计在界面禁用，服务仍再次校验。无需改动任务、音色、审核、导出或 WebUI 核心业务。
5. 运行适配器契约测试和真实推理验证。tests/fake_engine.py 是测试专用的第二适配器，不可作为真实 TTS 能力声明。

## 增加项目集成

导出适配器实现 folder(result) 返回相对目录，并在 export_adapters 中注册。适配器不能修改模型、任务或原始资产；具体引擎导入工具可读取 manifest.json 和逐音频 JSON。Godot、Unity、Unreal、剪辑工具均是输出消费者，不是平台核心依赖。
