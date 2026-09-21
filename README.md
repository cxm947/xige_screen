# xige_screen

[![Tests](https://github.com/cxm947/xige_screen/actions/workflows/test.yml/badge.svg)](https://github.com/cxm947/xige_screen/actions/workflows/test.yml) · [下载 v0.2.1](https://github.com/cxm947/xige_screen/releases/tag/v0.2.1) · [问题反馈](https://github.com/cxm947/xige_screen/issues)

从视频链接和主题出发，与用户一起找完整场景、写一场能听懂的戏、保留原场表演重录新词，最后逐句检查成片。

这是一个 **agent skill + 可运行的本地制作核心**。找片判断、编剧和表演试听由 agent 与用户协作；账本、缓存、时间映射、混音、编码和装配检查由脚本执行。不是“一键无审稿模仿所有演员”的服务。

## 安装与调用

从 [Releases](https://github.com/cxm947/xige_screen/releases/latest) 下载 `xige_screen-pro-0.2.1.zip`，解压得到 `scene-redub/`。同页提供 SHA-256 校验文件；GitHub 自动生成的 Source code 压缩包是源码快照，安装时也需保留完整技能目录。

把整个 `scene-redub/` 放入支持 SKILL.md 的宿主技能目录。Codex 用户可放到 `~/.codex/skills/scene-redub/`（配置了 CODEX_HOME 时用其 skills 目录）；不要只复制 SKILL.md。重新加载技能后输入：

> 使用 $scene-redub。视频链接：……；主题：AI 行业。先帮我确认完整饭局，再磨台词，最后配音。

核心账本命令只需 Python 3.10+；媒体命令需要 numpy 和 FFmpeg。可在独立虚拟环境安装：

```text
python -m pip install -r requirements-media.txt
python scripts/redub.py doctor
```

如果机器已有 FFmpeg 可直接用；否则 imageio-ffmpeg 提供二进制。需要 libx264、AAC、ass、loudnorm、aresample、asetpts。可选下载工具安装 `requirements-source.txt`；网站支持随源站变化，无可用链接时可导入本地文件。

配音模型单独配置，见 [后端说明](references/backends.md)。本包不安装 CUDA、不自动下载权重、不要求 API key。没有可用模型也能先完成片源、台词和参考清单；也支持导入其他工具的完整录音。

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

当前是单声道短场景工具。自动人声分离、ASR、声纹验证、口型重建、复杂重叠人声和云端配音 SDK 没有打包成内置功能；可用已有工具处理后导入。IndexTTS 适配器是可选后端，不作全平台 GPU 兼容承诺。配音质量必须通过真实试听判断。

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
