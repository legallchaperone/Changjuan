# 长卷 Pipeline 测试素材库

本目录存放用于测试 ASR → Extraction → Narrative pipeline 的真实音频素材。
所有素材均为公开发布内容，仅用于内部技术测试。

---

## 素材列表

| 文件名 | 来源 | 时长 | 语言/方言 | 讲述人 | 内容摘要 | 适合测试 |
|---|---|---|---|---|---|---|
| 四零后人生回忆录——我的姥姥姥爷.mp3 | [B站 BV1bYFWeBE8n](https://www.bilibili.com/video/BV1bYFWeBE8n/) | ~35min | 普通话（北方口音） | 82岁姥姥、姥爷 | 两位四零后老人讲述个人生平，含婚姻、家庭、历史变迁 | 基础 pipeline 跑通；P0 claim 抽取（年份/人名/地名） |
| 85岁老人讲述人生故事.mp3 | [B站 BV1j94y1973G](https://www.bilibili.com/video/BV1j94y1973G/) | — | 普通话 | 85岁老人 | 人生经历口述，含职业、家庭、感情经历 | 对比不同讲述人的 claim 密度；verifier gate 测试 |

---

## YouTube @jinguansh 待选素材（人工挑选后下载）

频道主要有三个 playlist，内容为老人口述人生故事，部分为繁体中文／台湾口音，待确认是否有方言内容。

| Playlist | 标题 | URL | 状态 |
|---|---|---|---|
| PL0UHbpXJ_Q14... | 長壽老人的生活 | [链接](https://www.youtube.com/playlist?list=PL0UHbpXJ_Q14aJ1y2U7m0FLzUGebKW-Pb) | ⏳ 人工挑选 |
| PL0UHbpXJ_Q15... | （标题待确认） | [链接](https://www.youtube.com/watch?v=-nxsfs0OKYU&list=PL0UHbpXJ_Q15GYrSUfC1OdJ7RDXe9ioy-) | ⏳ 人工挑选 |
| PL0UHbpXJ_Q17... | （标题待确认） | [链接](https://www.youtube.com/watch?v=sWAku61oNFQ&list=PL0UHbpXJ_Q17R0M1H1qz7VPDqA1OIEWBd) | ⏳ 人工挑选 |

挑好视频后用以下命令下载：

```bash
yt-dlp -x --audio-format mp3 --audio-quality 0 \
  -o "scripts/test_audio/%(title)s.%(ext)s" <视频URL>
```

---

## 其他待补充

| 来源 | 状态 | 备注 |
|---|---|---|
| 方言素材 | ❌ 缺 | 建议找粤语或闽南语老人采访，测试 ASR fallback 边界 |

---

## 使用方法

```bash
# 跑单个文件完整 pipeline
PYTHONPATH=packages:apps/api VENV/bin/python -m scripts.batch_ingest \
  scripts/test_audio/<文件名>.mp3 --model medium

# 输出保存在同目录 <文件名>.pipeline.json
```

## 下载新素材

```bash
yt-dlp -x --audio-format mp3 --audio-quality 0 \
  -o "scripts/test_audio/%(title)s.%(ext)s" <URL>
```
