# 配音后端与安装边界

本包不包含模型、权重、真人参考音或付费 API 凭据。核心项目／渲染环境与模型环境分开；模型安装使用各自上游说明，不让一个配音模型破坏全局 Python。

## 提供的本地适配器

`scripts/index_adapter.py` 接 IndexTTS 2.5 的 `IndexTTS2` 双参考接口。它读取项目的音色参考、表演参考和完整新词，保存实际模型／源码内容哈希、运行时与参数，注册 take；不自动判定演技、不自动联网下载。

在已可工作的 IndexTTS 环境运行，config.json 存在私有项目旁：

```json
{
  "repo": "/local/path/index-tts",
  "model_dir": "/local/path/IndexTTS-2.5",
  "runtime_paths": [],
  "device": "cuda:0",
  "use_bf16": true,
  "cpu_threads": 4,
  "lang": "ZH"
}
```

Windows 路径可写 `D:/Models/...`。runtime_paths 仅用于已验证的本地兼容环境，默认空；不预置任何开发者机器路径。可额外设置 ffmpeg。配置和项目都不放进 skill 发行包。

```text
<model-python> <skill>/scripts/index_adapter.py <project> --config <config.json> --turn turn_017 --dry-run
<model-python> <skill>/scripts/index_adapter.py <project> --config <config.json> --turn turn_017 --seed 117 --alpha 1 --select
```

--turn 可重复指定，小批量串行运行，避免显存互抢。第一遍自然时长；确实需要时才加 --duration-factor（0.5–1.35）。这个参数不是精确时间保证，生成后仍要检查。--select 只选素材，不意味着用户认可。

先对当前模型源码核查接口。适配器按 2.5 的 `(sample_rate, int16_PCM)` 返回值转换；返回契约变化时明确失败，不猜幅值。重新跑相同请求先核验收据与实际资产，缓存损坏不会静默跳过。

## 其他路线

| 路线 | 前提和取舍 |
|---|---|
| 带独立音色／表演参考的 TTS | 直接生成新词；先试同场原句参考，对准确词义和尾字逐句检查 |
| 表演录音＋voice conversion | 先有人／模型完整演好新词，再换声；换声器不负责创造缺失的表演 |
| 显式韵律控制模型 | 可能提供更强控制，也可能因新旧词差异出错；用代表性小样决定 |
| 后期时长／音高修改 | 小幅修复工具，不是默认质量提升；中文声调、气泡音和低信噪比容易出问题 |

外部 API 是否可用、成本、上传内容和供应商条件随时间变化，实际使用前按用户请求和当前工具能力核实。未调用的服务不能写成已实测。

## 一手资料

技术依据访问于 2026-09-21，后续使用应再核对版本：

- [IndexTTS 2.5 官方说明](https://github.com/index-tts/index-tts/blob/main/docs/README2.5_ZH.md)
- [IndexTTS 2.5 推理源码](https://github.com/index-tts/index-tts/blob/main/indextts/infer_v2_5.py)
- [ElevenLabs Voice Changer](https://elevenlabs.io/docs/eleven-creative/playground/voice-changer)
- [Seed-VC](https://github.com/Plachtaa/seed-vc)
- [Amphion Vevo2 推理入口](https://github.com/open-mmlab/Amphion/blob/main/models/svc/vevo2/infer_vevo2_ar.py)
- [Parselmouth 音高操作示例](https://parselmouth.readthedocs.io/en/stable/examples/pitch_manipulation.html)
- [FFmpeg filter 文档](https://ffmpeg.org/ffmpeg-filters.html)
- [yt-dlp 使用说明](https://github.com/yt-dlp/yt-dlp#usage-and-options)

链接说明技术来源，不代表项目合作、背书，也不授予第三方代码／模型／媒体的许可。
