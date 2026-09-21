# 开发与发布

这是工作流和本地制作核心，真实制作工程请放在仓库外。安装独立 Python 环境后：

```text
python -m pip install -r requirements-media.txt
python scripts/redub.py doctor
python -m unittest discover -s tests -v
```

模型适配器在它自己的可用环境中运行，不把 GPU 依赖塞进核心环境。复现问题时先记录 Python、FFmpeg 和后端版本。

## 本地开发示例

核心需要 Python 3.10+。下载片源时另装 `requirements-source.txt`。下面的示例使用合成色块和音调，不需要配音模型：

```text
python scripts/make_demo.py /path/to/demo-project
python scripts/redub.py render /path/to/demo-project
python scripts/redub.py status /path/to/demo-project
python scripts/revise_demo.py /path/to/demo-project
python scripts/redub.py render /path/to/demo-project
```

示例验证角色分句、剪辑时间映射和音轨合成；`revise_demo.py` 演示修改 A 后替换对应录音、复用 B。真实项目的数据结构与命令见 [项目契约](references/project-contract.md)。

核心测试不需要联网或模型。媒体测试需要 numpy 和 FFmpeg，缺少时会标记 skip。实际平台与模型验证记录见 [发布说明](RELEASE_NOTES.md)。

## 提交修改

报告具体的输入、命令、预期行为和实际错误。配音问题请提供句子 ID、时间范围、是词不清还是语气不对；可使用合成素材复现工程问题。不需要把完整影片、原声参考、模型权重、密钥或带个人目录的日志提交到 issue。

修复保持一个明确范围。涉及时间映射、音轨合成、缓存或编码时，测试观察真实输出及失败行为；文字说明修改不需要机械地增加测试。表演质量需要真实试听，合成音调只能验证工程链路。

## 构建发行包

从干净的源码目录运行，输出位置放在仓库外：

```text
python scripts/package_release.py --output ../scene-redub-release.zip
```

打包器接受 Git checkout，会跳过 `.git` 和 Python 缓存，其他文件仍按允许列表检查。它拒绝覆盖已有 ZIP，生成文件清单和 SHA-256。解压后重新打包，哈希应相同。

发布前核对版本与实际测试记录、解压安装、完整媒体导出及包中文件清单。CI 配置存在不等于 CI 已通过；未做的环境测试和未试听的演员效果写清楚。公开代码包不包含制作项目媒体。

Windows 推理依赖的直接输入在 `requirements-windows.txt`，实际解析的固定版本在 `requirements-windows.lock.txt`。修改后用独立 Python 3.11 环境安装，再核对 CPU / CUDA 分支；PyTorch 变体由安装器单独选择。模型与源码的版本、大小、SHA-256 分别在模型清单和安装器中，不跟随上游 latest。

复杂 Skill 发布按 skill-creator 流程检查 frontmatter、引用和脚本，再从解压包做独立制作验证。标准结构保持 `SKILL.md`、`agents/`、`scripts/`、`references/`、`assets/`；README、安装入口、测试与版本记录服务于本仓库的开源发布。大依赖只在首次使用时下载，不纳入 ZIP。
