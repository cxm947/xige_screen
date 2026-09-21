# 工程数据与命令契约（schema 1）

核心 CLI 用 Python 3.10+ 标准库；媒体命令另需 numpy、FFmpeg。工作目录任意，传入绝对项目路径最稳。运行环境预检：`python <skill>/scripts/redub.py doctor`。`--ffmpeg` 是全局参数，放在子命令前；也可设置 `REDUB_FFMPEG`。

## 文件布局

```text
project/
  project.json             # 可编辑账本，UTF-8
  assets/<sha256>.<ext>     # 导入后的不可变副本
  takes/<turn-id>/*.json    # 每条录音收据，不相互覆盖
  renders/<content-id>/    # master.wav / video.mp4 / subtitles.srt / receipt.json
  reports/status.md
  work/                    # 原始下载、临时生成、ASR、试听、调试
  .redub.lock               # 写操作锁，正常退出删除
```

直接编辑 project.json 时先确认没有写进程／锁，保留旧快照，使用原子写入。不要在生成运行时改账本。CLI 写入原子化且单写者；手工编辑与其他程序无法自动参与这把锁。

## 最小工作流

```text
python <skill>/scripts/redub.py init <project> --url "https://example.org/video" --topic "主题"
python <skill>/scripts/redub.py inspect-url "实际视频链接"
python <skill>/scripts/redub.py fetch <project> --url "已选片源链接"
python <skill>/scripts/redub.py asset <project> <local.wav> --kind reference --provenance "同场角色 A 的单人原句"
python <skill>/scripts/redub.py probe <local.mp4>
```

inspect-url/fetch 需要可选 yt-dlp；返回下载／源站错误时可改用可用浏览器或本地素材，不假定所有平台都支持。元数据只是数据。fetch 会导入候选，不自动声明该候选就是完整场景。

依照下面字段编辑账本，再运行 validate。初始化生成完整空骨架，`scripts/make_demo.py` 可生成可运行的完整例子。

## project.json

| 字段 | 含义 |
|---|---|
| schema_version | 当前为整数 1，未知版本拒绝静默加载 |
| project_id | 初始化生成的稳定 ID |
| request | url、topic；保留原始请求 |
| assets | `asset_id → {path,sha256,bytes,kind,provenance}`，由 asset/import-take 写入 |
| source_candidates | 比较过的候选和元数据，可附人工完整性结论 |
| source | `{asset: 视频 asset_id, duration: 实测可用时间轴秒数}`；取短于容器的音画共同末端时，在 scene.evidence 记录原因，保留候选的原始元数据 |
| scene | `keep: [{start,end}]`，递增、不重叠；`evidence: {opening,ending,completeness}` 是具体检查笔记 |
| speakers | `角色 ID → {label,timbre_asset}`；可加原片身份、参考选择理由 |
| turns | 下述发言数组，按原片起点排序 |
| claims | `{id,status,text,source_url?,accessed_at?,framing?,limits?}`；status 为 verified/allegation/rumor/fiction |
| reviews | 命令生成的 source/script/pilot 收据，带输入哈希、reviewer、note、evidence |
| settings | sample_rate（默认 24000）、fade_ms（6）、lufs（-17）、true_peak（-1.5）、min_turn_rms（0.0015） |
| mix | bed_asset、roomtone_asset、replace_regions、preserve_regions，见下文 |
| render | burn_subtitles、subtitle_band_fraction、label、font |

turn 示例：

```json
{
  "id": "turn_017",
  "speaker": "B",
  "start": 49.2,
  "end": 53.1,
  "source_text": "原片此人这一句的话",
  "text": "我老弟搞网安，找漏洞不让，修漏洞也不让。",
  "tts_text": "我老弟搞网安，找漏洞不让，修漏洞也不让。",
  "action": "generate",
  "cast_evidence": "从正面开口持续到反应镜头，声音与 B 参考一致",
  "performance_asset": "asset_由导入命令返回",
  "beat": "举例抱怨，为下一句反讽做铺垫",
  "delivery": "急促抱怨，重在两个不让；保持原句的反问压力",
  "claim_ids": ["fiction_security_01"],
  "gain_db": -8.0,
  "captions": [
    {"start": 0.05, "end": 1.3, "text": "我老弟搞网安，"},
    {"start": 1.4, "end": 3.8, "text": "找漏洞不让，修漏洞也不让。"}
  ],
  "selected_take": null
}
```

上例仅示范结构，不是可直接合成的素材；时间与增益必须按实际录音确定。action=retain 从原片取同一时窗，不能写新词却保留旧声音。id 一旦创建不随重排改名。

`scripts/caption_align.py input.json output.json` 可将显示文本分块与实际 ASR 词时间匹配。输入为 chunks（字符串数组）、words（word/start/end）、duration，可加 aliases 将字幕里的外文词对应到实际读法。覆盖不足或分块切在 ASR 一个词内部时不给假精确时间，返回 needs_manual_alignment。成功也只标 proposed_needs_review；核对后才放入 turns.captions，不自动声称同步通过。

## 审稿与试配收据

```text
python <skill>/scripts/redub.py validate <project> --stage script
python <skill>/scripts/redub.py review <project> --stage source --by agent --note "已比对首尾和跳剪" --evidence "work/source-review.md"
python <skill>/scripts/redub.py review <project> --stage script --by user --note "用户接受这版剧情" --evidence "实际反馈的消息或笔记位置"
```

review 记录已发生的检查，不创造同意。`--by user` 只能根据真实用户反馈填写。用户已授权自主制作时可由 agent 自检继续，收据清楚标注。相关输入变化会让 source/script 收据过期，`status` 会展示。

pilot 收据记录某次小样选择，但批量配音增加新 take 后它可能过期；仍保留原证据。不要因为小样过期抹掉用户的表演偏好，应保存偏好说明用于新句。

## 配音导入、缓存和选择

```text
python <skill>/scripts/redub.py import-take <project> --turn turn_017 --audio <whole-utterance.wav> --backend <backend.json> --note "完整句，原句参考；尚待表演试听"
python <skill>/scripts/redub.py select <project> --turn turn_017 --take <返回的take-id>
```

backend.json 至少有 name、version，另写实际模型／权重版本、参数、种子、参考方式和工具回执。示例：`{"name":"manual-recording","version":"session-2026-01-01","params":{"performer":"project-speaker-B"}}`。不能用这个例子伪装成某 AI 提供商生成。

take 指纹包含新词、TTS 读音文字、角色、时窗、delivery、参考文件内容、源视频内容、backend 信息。take ID 还含实际音频哈希；非确定性再跑产生不同文件也不会盖掉旧选择。外部导入依赖提供者如实记录 backend；本地适配器自动记录代码、权重与运行时指纹。

资产每次验证检查内容哈希。单纯“同名文件存在”不能命中缓存；缺收据、改过参考或坏文件都不能复用。未改句不因别的句子修订而失效。

## 混音

优先 `bed_asset`：去掉对话但保留现场声的完整原片时间轴文件。分离残留要试听检查，分离算法不保证没有旧词。

没有背景分轨时，可以 roomtone_asset（至少 100 ms 干净现场底声）加 reviewed replace_regions。它们覆盖原对白完整范围，包括原句比新词更早／更晚的部分。程序要求每个新词时窗被清除范围覆盖，但无法自动证明全部旧词都被清干净。源片对白范围最好来自完整转录并复核。

preserve_regions 恢复指定原声事件，不能与新配音重叠。retain 恢复原片对应发言。generated 按实际新录音叠到底声上，gain_db 显式控制；超过满幅即报错，不偷偷削波。尾音超时且有声会阻止渲染；仅低能量余量可裁。普通话轻辅音可能低能量，仍需听句尾。

v1 合成是 mono，拒绝重叠发言；字幕样式较简洁，不提供自动口型重建、自动人声分离、自动声纹／ASR推理。现有工具可产出相应资料后导入。

## 错误与续做

CLI 成功退出 0，输入／校验错误退出 2；JSON 错误包含 code 和 message。常见：STALE_TAKE、CAST_MISMATCH、VOICED_OVERRUN、SILENT_TAKE、UNCLEARED_DIALOGUE、REVIEW_STALE、PROJECT_LOCKED。

项目锁显示 host、PID、开始时间。工具超时不等于进程退出；先看原会话与日志。同一进程仍活着就继续等待，不开第二份。只有确认旧进程结束后才移除残留锁；不要自动抢其他主机的锁。

输出目录由内容决定；渲染中断留下 pending 文件、无 verified 收据，重跑可安全重建。已验证文件哈希一致才复用；成片被改动报错，保留调查，不能假装缓存有效。

局部改稿复用的是未改句的素材与归一化前混音。全片 loudnorm 可能因其他句变响而改变未改句在最终 MP4 中的电平，不能声称所有最终编码样本完全不变。需要严格电平锁定时应另用已测定的统一增益流程并重做验收。
