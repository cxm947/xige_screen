# Windows 安装与完整制作

## 用户只需做什么

下载 Release 的 Skill ZIP，先解压，双击 `Install.cmd`。安装会自动配置独立 Python 3.11、FFmpeg、PyTorch 和 IndexTTS 2.5，下载并校验约 7.1 GB 模型，再用本机 Windows 系统语音作为参考，实际生成一条新台词、合成 MP4。安装成功后，在支持本地工具的 ChatGPT 桌面 Work／Codex 中选中 `scene-redub`，给视频链接和主题。

ZIP 本身只放技能、脚本和依赖清单，不包含 Python 本体或大模型。如果已经通过客户端安装了技能，直接调用即可：`Run.cmd` 检测到环境未就绪时自动安装，装好后继续原命令。Python、PyTorch 和配音模型只在首次安装时自动下载；已经校验通过的文件会复用。

无需预装 Python、Git、CUDA Toolkit 或配置 API key。需要联网完成首次下载；下载速度取决于 GitHub、PyPI、PyTorch、Hugging Face 的连接。Windows x64；NVIDIA 显卡、驱动与可用内存满足条件时选择 CUDA，否则自动使用 CPU。CPU 模式显著较慢。建议 32 GB 内存、至少 25 GB 空闲硬盘；NVIDIA 显卡建议 12 GB 以上显存。显卡驱动由 Windows／NVIDIA 安装；本包不修改驱动。

自动选择会检查第一张显卡的总显存、当前空闲显存及 Windows 剩余提交额度：至少约 10 GB 总显存、8 GB 空闲显存、20 GiB 剩余提交额度才尝试 CUDA，再检查 BF16 支持。Windows 的 GPU 推理也占系统提交额度，因此有独显不代表当前资源足够。`-Device cuda` 可明确选择 GPU，需自行满足可用资源；内存不足时用 `-Device cpu`，不修改系统分页文件或关闭其他应用。

技能可被客户端识别与本机引擎能运行是两个条件。安装器把技能放入现有的 `CODEX_HOME/skills/scene-redub` 或标准用户 `.agents/skills/scene-redub`。官方 [技能说明](https://learn.chatgpt.com/docs/build-skills) 说明桌面技能、本地发现与调用入口。ChatGPT 用 `@` 选择，Codex 可用 `$scene-redub`；尚未显示时刷新／重启客户端。需要本地工作模式及本地文件、程序执行权限；仅上传 ZIP 到云端聊天不会安装本地引擎。

## 环境与项目分开

默认运行环境位于 `%LOCALAPPDATA%/xige_screen/`，包含 `env/`、`python/`、`models/`、`engine/`、`skill/`、`checks/` 与 `logs/`。影片制作放在另一个项目目录。删除一个影片项目不会删掉引擎。

可以指定位置，例如：

```powershell
.\Install.cmd -InstallRoot 'D:/xige_screen'
```

路径支持空格和中文。不修改系统 PATH 或全局 Python。解压目录与安装后技能目录的 `runtime.json` 都记录持久引擎位置；这个私人定位文件不进入发行 ZIP。升级时解压新包，使用原 InstallRoot 再装；已有模型必须通过哈希校验才会复用。

安装过程中断后，重新双击同一个 `Install.cmd` 即可续装。日志在引擎 `logs/`；还在运行时不要再开一份。若 CUDA 驱动不可用，先升级驱动，也可明确使用 `Install.cmd -Device cpu`。`-ModelCache` 可复用另一处完整模型缓存；仍校验全部模型文件。`-NoSkillInstall` 和 `-SkipVoiceTest` 仅用于工程检查；跳过语音测试不能当作完整安装验收。

## 给 agent 的命令

先解析 `<skill>/runtime.json`。以下使用 `<skill>/Run.cmd`，不用系统 Python，也不用自己找后端配置：

```text
Run.cmd doctor
Run.cmd core init <project> --url <URL> --topic <主题>
Run.cmd core inspect-url <URL>
Run.cmd core fetch <project> --url <URL>
Run.cmd transcribe <video> --language zh --model small --word_timestamps True --output_dir <project>/work/asr
Run.cmd prepare <new-project> --video <video> --plan <scene-plan.json>
Run.cmd generate <project> --turn turn_001 --turn turn_002 --select
Run.cmd core render <project> --preview
Run.cmd core status <project>
```

`transcribe` 首次自动下载选定的 Whisper 模型到持久引擎；模型推理和 Whisper 串行运行，避免抢显存。ASR 不负责判断反应镜头的说话人，也不代表表演试听。

已核对的 `scene-plan.json` 最少包含：`topic`、`source_evidence`（opening/ending/completeness）、`speakers`、`turns`，以及 `bed_file` + `bed_evidence` 或 `roomtone` + `bed_evidence` + `replace_regions`。可选 `url`、共同音画 `duration`、`keep`、`claims`、`render` 和 `preserve_regions`。所有时间均为原片秒数。

`speakers` 是角色 ID 到 `{label, reference:[起点,终点], evidence}` 的映射。`turns` 沿用 [项目契约](project-contract.md) 的 id/speaker/start/end/source_text/text/cast_evidence/delivery/beat 等字段；`performance:[起点,终点]` 可单独指定对应原句参考，默认使用该句时窗。脚本自动提取参考、复制素材、绑定哈希；不自动宣称审稿或听感合格。短参考不能含另一个人的声音。

对已有项目不要重复 `prepare`，修改原账本后校验并只重录受影响的完整句。需要自定义处理时用 `Run.cmd python <脚本> ...` 调用同一个受控环境。整片合成前记录实际完成的 source/script review；`--preview` 仅允许跳过编辑确认，不跳过角色、尾音和空轨检查。

## 安装自检的含义

`Run.cmd self-test` 使用 Windows 自带系统语音做参考，由 IndexTTS 合成不同的新句，然后运行真实项目账本、配音收据和 MP4 编码流程。`checks/latest.json` 记录实际路径、耗时与最终音轨检查。它验证依赖安装、真实模型推理和视频装配；不证明任意演员复刻质量。演员语气仍按原片→改词小样试听。
