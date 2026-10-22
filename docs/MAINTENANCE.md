**简体中文** | [English](MAINTENANCE.en.md) | [日本語](MAINTENANCE.ja.md) | [한국어](MAINTENANCE.ko.md)

# 维护、恢复与更新

## 日常运行

在安装目录双击 `start-voice.cmd`、`stop-voice.cmd` 或 `check-health.cmd`。启动脚本也会打开 WebUI。

- `voice start / health / stop`；没有注册系统服务或开机任务。
- `voice unload` 释放本平台模型；空闲默认 300 秒自动卸载。不终止其他软件。
- runtime/logs/platform.log 为轮换异常日志，server.log 为启动和官方模型输出。
- 运行参数统一在 config/platform.json；改路径时停服务，复制资产与数据库并备份后再更新路径。不要直接移动模型目录而保留旧配置。
- 一次只运行一个服务进程和一个 GPU 任务；service.lock 进程租约防止重复工作线程消费同一队列。

## 备份

在安装目录执行：

~~~powershell
bin\voice.cmd backup
~~~

该命令通过 SQLite 在线备份机制保存一致数据库与配置，位置 data/backups/<UUID>。这不等于完整音频备份。完整备份需额外保存 data/references、data/recordings、data/reference-comparisons、data/audio-processing、data/originals、data/exports、models 下各模型的 provenance.json 和源码/依赖锁；大权重可凭固定版本重下。

完整复制数据目录期间应停止服务，以保持数据库和文件一致；替换前先另存当前数据。

全局注册前的用户 PATH 和 Codex 配置备份在 data/backups/global-<时间>。备份可能包含私有配置，不上传、不贴到日志。

恢复步骤：停止平台，另存当前 data，将备份 SQLite 和匹配的音频目录放到配置位置，校验模型与参考哈希，启动并查看 health 与任务。中断生成转失败，可重试；原有结果不覆盖。不要删除不明 partial 文件来“修复”资产。

## 更新

先备份。新模型或代码先用新配置/隔离环境验证，再切换。权重原地变化时旧任务因身份不匹配拒绝执行；需要创建新任务。不要 `pip install -U` 全环境。记录 Python、CUDA wheel、官方源码 commit、模型 revision、依赖锁和真实试音。

平台版本 0.1/0.2/0.3 的数据库 schema 为 1，保留稳定 UUID 与 JSON 实体。0.2 新增录音、参考对比实体和可选归档字段，0.3 新增 audio_processing 实体和派生录音来源，旧任务缺省为未归档，不重写历史音频。未来 schema 改动必须新增备份和显式迁移，不能以删除数据库代替迁移。

任务归档在「任务队列」切换当前/已归档，可单个或批量恢复。设置 `task_archive_after_days=0` 关闭自动归档，默认 7 天；仅已结束任务参与。归档保留音频与审核，不用于释放磁盘空间；恢复重新计时，归档任务重试不会继承归档状态。可直接用原任务 UUID 查询历史结果和事件。

## 常见问题

- 连接失败：先 `voice start`，查看 runtime/logs/server.log。端口冲突通过统一配置修改，不重复开启 worker。
- 显存不足：先停止或卸载本平台任务，手动关闭其他占用；平台不会擅自停止别的软件。保留失败任务并重试。
- 语速或情绪不符合：自然语言为近似控制，调整描述或增加候选并试听，不将它包装为精确参数。
- 长文漂移：选择已确认参考、相同模型与配置；段间韵律仍需人工检查。
- 非 WAV 导出失败：检查 FFmpeg 与对应编码器；原始 WAV 保留。声道复制不等于创造真实立体声空间。
- 字幕裁剪冲突：关闭裁剪或字幕；精确词级对齐未配置时不生成伪造词时间戳。
- 全局命令不可见：新开终端；Codex 新 MCP 需重启或重载。可先直接调用安装根目录 bin/voice.cmd。
- 批量失败：逐任务查看 error / events；已有成功输出与审核状态保留。

## 验证边界

单元测试使用测试专用合成波形验证业务契约；真实模型验证另行运行。技术音频有效、浏览器操作、人工听感与正式生产验收分开记录。任何自动化成功均不自动批准音频。

## 0.4 长文与回收站

完整备份新增 data/longform（原始文本、规范化文件、每段/每次音频、后台导出）；SQLite 在线备份包含 lf_* 索引、审核历史和 asset_trash。0.4 增量增加表/列/索引，旧 UUID 和文件保留。模型与人物配置冻结在作品中，不通过修改全局配置偷偷改变半本书。

恢复后中断段回到 pending，作品暂停等待明确续作；导入中断可从保留原件重新解析，导出中断可重新提交。不要删数据库或重建整个音色库来处理个别失败段。原件哈希变化会阻止继续使用。

回收站用于整理和恢复，不释放磁盘。删除章节/分段后统计重新计算，受影响章节需要重审；恢复整批保留关联，恢复章节不会复活此前单独删除的段。没有不可恢复清空按钮。当前源字节上限、分段/自动分章/块大小统一在 longform 配置。

大文件验证脚本 scripts/verify_longform_scale.py 使用独立 8962 服务和 runtime/longform-scale，结束后关闭自己的服务；大样本文本不写入用户作品库。该目录是验证材料，不作为正式声音或用户内容。

## 相关说明

[README](../README.md) · [安装说明](INSTALL.md) · [长文配音](LONGFORM.md) · [参考音频](REFERENCE_PREPROCESSING.md) · [音频处理](AUDIO_RESTORATION.md)
