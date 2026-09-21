# xige_screen

[![Tests](https://github.com/cxm947/xige_screen/actions/workflows/test.yml/badge.svg)](https://github.com/cxm947/xige_screen/actions/workflows/test.yml) · [下载 Skill](https://github.com/cxm947/xige_screen/releases/latest) · [问题反馈](https://github.com/cxm947/xige_screen/issues)

从视频链接和主题出发，与用户一起找完整场景、写一场能听懂的戏、保留原场表演重录新词，最后逐句检查成片。

这是一个 **桌面 agent 技能 + Windows 自动安装的本地配音引擎**。找片判断、编剧和表演试听由 agent 与用户协作；账本、缓存、时间映射、混音、编码和装配检查由脚本执行。不是“一键无审稿模仿所有演员”的服务。

## Windows：下载、解压、双击安装

1. 从 [Releases](https://github.com/cxm947/xige_screen/releases/latest) 下载 `xige_screen-skill-0.3.0.zip` 并解压。
2. 双击 `scene-redub/Install.cmd`。自动下载独立 Python、FFmpeg、推理依赖和约 7.1 GB 模型，不需要自己配 Python、Git、CUDA Toolkit 或 API key。
3. 安装会真实生成新语音并合成测试视频，通过后把技能安装到本地技能目录。
4. 在支持本地工具的 ChatGPT 桌面 Work／Codex 里选择 `scene-redub`，输入视频链接和主题。ChatGPT 用 `@` 选择，Codex 可用 `$scene-redub`。

**小技能包＋首次自动配置环境**：ZIP 不包含 Python 本体、PyTorch 或模型权重。如果先通过客户端装好了技能，首次调用时也会自动安装缺少的环境，然后继续任务。以后复用已验证的环境与模型。

> 使用 scene-redub。视频链接：……；主题：AI 行业。按原场景的剧情和人物语气改词，先让我听小样，再配完整段。

首次需联网下载。Windows x64，建议 32 GB 内存、25 GB 空闲磁盘、12 GB 以上 NVIDIA 显存；没有适用显卡、或当前可用内存不足时自动用 CPU，速度较慢。安装环境与影片项目独立，清理视频中间文件不会删除模型。自定义安装盘、续装、诊断、实际制作命令见 [Windows 指南](references/windows.md)。

这是运行本地工具的桌面技能：仅把 ZIP 上传到普通云端聊天不会让它使用你的电脑和 GPU。客户端须支持本地技能与程序执行。当前官方入口见 [OpenAI 技能说明](https://learn.chatgpt.com/docs/build-skills)。

双击 `Run.cmd` 查看用法；`Run.cmd doctor` 检查环境，`Run.cmd self-test` 再次验证真实推理与视频合成。安装的模型源码和文件哈希锁定；后续安装复用校验通过的下载。

## 其他环境／已有后端

核心 Python 3.10+ 仍可独立运行：`python -m pip install -r requirements-media.txt`，然后 `python scripts/redub.py doctor`。下载片源另装 `requirements-source.txt`。其他平台的模型环境按 [后端说明](references/backends.md) 配置；Windows 自动安装流程专门处理本地推理依赖。

## 无模型的可运行例子

```text
python scripts/make_demo.py /path/to/demo-project
python scripts/redub.py render /path/to/demo-project
python scripts/redub.py status /path/to/demo-project
python scripts/revise_demo.py /path/to/demo-project
python scripts/redub.py render /path/to/demo-project
```

示例生成五秒色块和两种合成音调，删掉中间半秒，验证人物账本、剪辑映射、音轨和编码尾部。revise_demo 演示只改 A、触发旧 take 失效、换入完整新 A、复用 B。它不演示真人声线质量。

真实制作从 `redub.py init` 开始，按 [数据契约](references/project-contract.md) 填写账本。完整能力入口见 [SKILL.md](SKILL.md)。

## 工程特点

- 台词逐次换人，固定 ID；源时间与成片时间分离。
- 配音绑定文字、角色、参考内容、参数和后端版本；变化时失效，未改句复用。
- 原子 JSON、单写者锁、不可变 take、内容寻址版本；超时后先检查原进程。
- 拒绝静音、串角色收据、越窗有声尾音、重叠发言与覆盖原声名句。
- 对最终 MP4 解码，逐段核对声音和混音，不把“生成文件存在”当完成。
- 事实／指控／传闻／虚构账本，以及用户与 agent 分开的审稿收据。

## 能力边界

当前是单声道短场景工具。Windows 包提供 IndexTTS 配音、Whisper 转录入口和视频装配；自动人声分离、声纹验证、口型重建、复杂重叠人声和云端配音 SDK 不在内置功能中。背景分轨或干净现场底声按原片情况准备；配音质量仍需真实试听。

支持相对资产路径和 UTF-8。测试平台及实际测试结果见 [RELEASE_NOTES.md](RELEASE_NOTES.md)；CI 定义不等于对应平台已经跑过。

## 测试

```text
python -m unittest discover -s tests -v
```

核心测试无联网／模型需求。媒体测试需 numpy 和 FFmpeg，缺少时明确 skip，不能把 skip 当媒体通过。故障用例覆盖参考变化、陈旧 take、角色错配、裁切穿句、静音、尾字超时、残留项目锁、损坏资产和 AAC 成片尾部。

## 发布内容

发行包只含原创工作流、脚本、文档、测试和合成示例生成器。没有原电影、真人声音、私人文档、模型权重、密钥或项目绝对路径。依赖和模型分别受其上游许可约束。项目不隶属于任何模型厂商或电影制作方。

本包原创内容使用 MIT 许可，见 [LICENSE](LICENSE)。第三方说明仅链接，未复制第三方 skill 正文。发布工具会按允许列表打包、检查常见私人路径／密钥模式并生成 SHA-256 清单；扫描不能代替人工检查新加入的文件。

源码贡献、问题报告和从 Git checkout 构建发行包，见 [CONTRIBUTING.md](CONTRIBUTING.md)。
