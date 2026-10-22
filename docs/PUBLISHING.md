# 发布和更新源码

公开版本与日常配音数据分开。运行环境、模型和用户资产留在安装目录，仓库只接收源码与许可资料。

生成公开副本：

```powershell
.venv/Scripts/python.exe scripts/package_public.py --dest ..\voice-foundry-public-next
```

目标目录必须不存在，脚本不会覆盖已有文件。它使用文件清单挑选源码，排除 data、models、vendor、runtime、.venv、examples、dist 和 docs/evidence，也不带测试录音或生成结果。历史验收文件保留在本机，公开版改用测试说明。

发布前，在副本里运行 Python 核心测试和主题测试，检查 `PUBLIC_SOURCE_MANIFEST.json`。不要把旧的备份压缩包直接放进 GitHub Release；这些包原本用于本机恢复，可能带有运行资料。

提交时显式选择源码目录和文件。不要在日常使用目录里执行 `git add .`。`.gitignore` 是补充保护，不能清除已经进入 Git 历史的内容。

公开仓库不提供自己的模型镜像。安装脚本从上游拉取固定版本；升级版本时，应检查代码、权重许可和校验值。若要发布带环境或模型的整合包，需要另查实际分发的文件和许可义务。
