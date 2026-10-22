# API v1 与全局调用

基础地址 `http://127.0.0.1:8961/api/v1`，OpenAPI `/openapi.json`。REST 是主契约；WebUI、CLI、MCP 都通过它工作。

| 功能 | HTTP |
|---|---|
| 健康、能力、系统 | GET /health、/models、/settings |
| 保存运行设置 | PUT /settings，修改空闲卸载、分段字数/停顿与队列上限，自动备份 |
| 卸载模型 | POST /models/unload |
| 项目 | GET/POST /projects |
| 音色列表/创建 | GET/POST /voices |
| 音色详情/新版本 | GET/PUT /voices/{id} |
| 音色历史 | GET /voices/{id}/versions |
| 参考上传 | POST /references，multipart: file、source、authorization、rights_confirmed |
| 参考列表/试听 | GET /references、/references/{id}/audio |
| 异步录音预处理 | POST /recordings，multipart: file、source、authorization、rights_confirmed，返回 202 |
| 录音与候选片段 | GET /recordings、/recordings/{id}、/recordings/{id}/original |
| 保存独立候选 | POST /recordings/{id}/save，reference_ids 数组，不拼接 |
| 停止/重试预处理 | POST /recordings/{id}/cancel、/recordings/{id}/retry |
| 编辑转写 | PUT /references/{id}/transcript，text、confirmed，保留历史 |
| 克隆对比 | POST /reference-comparisons，voice_id、reference_ids、text、seeds、clone_mode |
| 对比状态与建议 | GET /reference-comparisons、/reference-comparisons/{id} |
| 显式应用主参考建议 | POST /reference-comparisons/{id}/apply，保存新草稿版本，保留其他参考 |
| 异步生成 | POST /jobs，返回 202 与任务 UUID |
| 批量生成 | POST /batches，items 数组，整批校验后入队 |
| 任务列表/状态 | GET /jobs（默认未归档，archived=true 仅归档）、/jobs/{id}（始终可查） |
| 分页任务 | GET /jobs/page，archived、project_id、status、limit（默认 50、最大 200）、offset，返回 items/total |
| 归档/恢复 | POST /jobs/archive、/jobs/restore，job_ids 数组（最多 200）；仅已结束任务，整批先校验 |
| 取消/重试 | POST /jobs/{id}/cancel、/jobs/{id}/retry |
| 增量事件/SSE | GET /jobs/{id}/events、/jobs/{id}/stream |
| 流式音频块 | GET /events/{event_id}/audio |
| 结果列表/详情 | GET /results、/results/{id} |
| 原件与分段字幕 | GET /results/{id}/audio、/results/{id}/subtitles |
| 人工审核 | PUT /results/{id}/review |
| 导出 | POST/GET /exports，GET /exports/{id}/download |
| 备份/停止 | POST /maintenance/backup、/maintenance/stop |
| 日志 | GET /logs |

```python
import httpx, time
base = 'http://127.0.0.1:8961/api/v1'
job = httpx.post(base+'/jobs', json={
    'text': '故事，就从这里开始。', 'title': '开场旁白',
    'style': '沉稳成年男性，温暖自然', 'seed': 42,
    'candidates': 2, 'streaming': True
}).json()
while job['status'] not in {'succeeded','failed','cancelled'}:
    time.sleep(1)
    job = httpx.get(base+'/jobs/'+job['id']).json()
print(job)
```

任务冻结模型版本、音色及参考、参数、种子、依赖。status: queued → running → succeeded/failed/cancelled。取消运行任务先进入 cancel_requested，下一片段/分段边界停止。服务中断的 running 任务转 failed，保留输出；queued 任务恢复执行。重试创建新任务并保留原任务与冻结配置。

不同引擎的可选参数放在 `engine_options` 对象中，仅允许该引擎 capabilities.parameters 声明的键、类型与范围。例如 VoxCPM2 为 `{"cfg_value":2.0,"inference_timesteps":10}`。音色可保存默认 engine_options；请求只覆盖明确提供的键。界面根据能力声明生成高级控件，新引擎不需要增加专属业务表单。

音色支持 `reference_ids` 和 `reference_scenarios`，`reference_id` 是主参考。生成请求可用 `reference_id` 覆盖本次参考；每次只传入一个文件。`clone_mode="hifi"` 需要模型声明 `hifi_cloning` 和非空参考转写；未人工校对的转写仍可生成预览，但保留未确认标记。VoxCPM2 声明 `hifi_style_control=false`：Hi-Fi 不采用人物默认描述，显式非空 style 会被拒绝，避免将其当台词朗读；实际控制策略保存在 pipeline.control_note。需要额外演绎引导时使用 reference 模式。任务冻结最新参考、转写版本和模型配置，后续编辑不影响旧结果。预处理来源、阈值、限制及操作例子见[参考预处理文档](REFERENCE_PREPROCESSING.md)。

`PUT /settings` 可增加 `task_archive_after_days`（0–3650，默认 7，0 禁用）。旧客户端省略此字段会保留现值。自动归档仅处理 succeeded/failed/cancelled，从 finished_at 起计；历史任务缺少完成时间时使用更新时间或创建时间，恢复任务从 restored_at 重新计时。服务启动、任务间及列表读取时检查，间隔至少约一分钟，长生成期间列表请求也会触发检查。归档只改变任务整理字段和事件，不改变生成状态、音频、结果审核或正式导出要求。

CLI：`voice jobs --archived`、`voice archive-job <UUID>`、`voice restore-job <UUID>`。MCP：`voice_archive_jobs(job_ids, restore=false)`，restore=true 恢复。所有工具共用同一服务。

SSE 的 audio_chunk 事件包含片段事件 UUID、segment、chunk、duration。收到后立即 GET /events/{id}/audio 获取独立 WAV 块；块按事件顺序拼接。SSE 结束事件为 end。客户端重连可重新读历史事件并按 UUID 去重。流式是固定文本输入的增量音频输出，不是边输入文本边解码。

审核 approved 要求 listened=true 和实际用户确认；系统不能用自动化测试或波形验证代替用户听感。所有最初结果为 pending。MCP 故意不暴露批准工具。

导出 naming 支持 {title} {candidate} {id} {voice_id} {project_id}，额外附加结果短 ID 以免重名。HTTP 导出仅写平台 data/exports；CLI/MCP 在用户明确指定的目标目录下建立唯一子目录，不覆盖现存文件。

## Codex 自然语言示例

- “查询声场模型能力，为这段文字生成沉稳的男性旁白，给我两个候选。”
- “在声场中创建角色草稿音色，保存这个描述和种子。”
- “列出全局音色，使用之前的旁白 Voice ID 重新生成这批台词。”
- “按脚本角色分别指定音色，提交批量任务。”
- “将已经人工批准的这些结果导出到当前项目的指定目录。”

MCP 工具名称以 voice_ 开头。接口不依赖 Codex；其他 MCP 客户端可用同一个 stdio 启动命令。用户未明确授权的项目目录不得作为自动导出目标。

## 0.3 智能参考与修复 API

新增路由、字段、CLI/MCP 入口及流程见 [AUDIO_RESTORATION.md](AUDIO_RESTORATION.md#开放调用)，在线 OpenAPI 为准确请求契约。原路由保持兼容；HTTP 上传的 smart_reference 缺省 false，WebUI/CLI/MCP 简易入口显式使用 true。原件、处理输出和派生参考都有独立 UUID 与来源，不覆盖历史资产。

## 0.4 长文 / 删除 / 批量审核

| 功能 | /api/v1 路由 |
|---|---|
| 整本导入与分页作品 | POST /longform/books（multipart）；GET /longform/books?limit&offset |
| 状态、配置、原文 | GET /longform/books/{id}、/configuration、/source |
| 编码重试 | POST /longform/books/{id}/retry-import，encoding |
| 分页章节/分段 | GET /longform/books/{id}/chapters；/chapters/{n}/segments?limit&offset&status |
| 连续试听 | GET /longform/books/{id}/chapters/{n}/next-audio?after；/segments/{n}/audio |
| 尝试追踪 | GET /longform/books/{id}/segments/{n}/attempts |
| 续作、暂停、失败重试 | POST /longform/books/{id}/resume、/pause、/retry-failed；resume/retry-failed 可带 chapter_no |
| 单段重试/新版本 | POST /longform/books/{id}/segments/{n}/retry、/regenerate |
| 逐章审核 | POST /longform/books/{id}/chapters/{n}/review，批准要求 listened=true |
| 后台导出 | POST /longform/books/{id}/exports，chapter_no/mode/format/draft；GET 同路径分页查询 |
| 导出状态/取消/下载 | GET /longform/exports/{id}；POST /cancel；GET /download |
| 管理类别与分页 | GET /assets/kinds；GET /assets?kind&deleted&limit&offset&book_id |
| 关联预览与删除 | POST /assets/delete-preview、/assets/delete，items:[{kind,id}]、cascade |
| 恢复 | POST /assets/restore，items；POST /assets/restore-batch/{batch_id} |
| 原子批量审核 | POST /results/review-batch，result_ids/status/listened/note/reviewer |

长文上传不受普通 GenerationInput 的 6 万字符字段限制，接收保护默认 2 GiB 源字节。章/段管理 ID 为「作品 UUID:章节号/全局段号」。删除是可恢复标记，不清空文件；忙碌状态/参考绑定会阻止整批执行。原路径保持可用于审计和恢复；不能把回收站当作不可恢复的数据擦除。

普通和长文克隆使用现有 clone_mode=reference / hifi，与“可控声音克隆 / 极致克隆”界面名称对应。新 MCP 连接共 33 工具，包含整本导入、分页、续作、导出、资产预览删除和恢复；没有批准音频的 MCP 工具。CLI 与详细流程见 [LONGFORM.md](LONGFORM.md)。

章节目录支持 `limit`、`offset`，也可用 `after=<章号>` 获取该章之后仍有效的章节。`after` 与 `offset` 可组合；下一章可请求 `chapters?after=当前章号&limit=1`，避免假定章号连续。
