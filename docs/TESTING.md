# 测试与验证范围

核心测试使用临时数据库和测试音频，不需要下载模型，也不读取用户录音：

```powershell
.venv/Scripts/python.exe -m pytest -q
node --test tests/workflow.test.cjs tests/theme.test.cjs tests/i18n.test.cjs
```

Python 测试检查任务、音色版本、参考音频流程、归档、长文分段、编码、审核、导出、删除与恢复。界面测试检查配色、语言识别、语言偏好、四语言词条、占位符和草稿恢复边界。测试引擎生成的是测试波形，不能据此判断模型的克隆效果。

真实模型测试需要先完成模型安装，再运行 `scripts/verify_model.py`。它验证本机 CUDA 下的 TTS、声音设计、合成参考克隆和流式输出。部分工作流脚本需要它生成的临时样音，请先读对应脚本。测试输出留在本机，不随公开源码分发。

开发时在 Windows 11、RTX 4090 上做过真实模型小样测试，也单独测试过千万级字符的导入和索引。没有执行千万级字符的全书语音生成，也没有在所有显卡、所有 Windows 安装环境上验收。

公开版本不带历史录音、截图或生产数据。运行测试后应检查自己的输出，人工听感、人物授权和正式内容审核仍由使用者确认。代码检查或自动化测试通过，不会自动批准任何音频。

若系统临时目录不可写，可为 pytest 指定一个尚不存在的目录：`--basetemp runtime/pytest-local-new`。每次使用新目录，避免覆盖其他测试资料。

安装检查与测试分开运行：`scripts/check_install.py --profile core` 检查当前目录的专用 Python、服务导入和 WAV 读写；`--profile inference --models` 还检查 CUDA、推理源码导入及模型文件。安装日志和结果在 `runtime/install.log`、`runtime/install-check.json`，不随源码分发。
