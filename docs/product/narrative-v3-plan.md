# 长卷 Narrative Pipeline V3 实施计划

**版本：** V3  
**状态：** 待执行  
**适用音频：** 已完成 ASR + fragment 提取的 pipeline.json  
**核心目标：** 消除正文虚构细节，每句话可追溯到讲述者原话

---

## 一、问题诊断

### 1.1 现象

V2 管道（`scripts/narrative_agent.py`）输出的章节正文中，约 60–70% 的细节是模型自行编造的，并未出现在讲述者的原始录音中。

**对比示例：**

| 正文内容 | 实际原话中是否存在 |
|---|---|
| "那间土房不大，进门就是灶台，旁边摆着一张木桌和两把竹椅" | ❌ 不存在 |
| "母亲常常站在灶台前，一边搅动锅里的粥" | ❌ 不存在 |
| "听到枪声，躲到床底下" | ❌ 不存在 |
| "脸上抹得漆黑漆黑的，把土都抹在脸上到处逃" | ✅ 存在（原话） |
| "捂着我，把我抱在怀里，暖着我" | ✅ 存在（原话） |

### 1.2 根本原因（三层）

**原因一：Writer 拿到的是摘要，不是原话**

现有代码（`write_chapter` 函数，约第 570 行）传给 Writer 的是：
```python
{"id": e["event_id"], "summary": e["summary_1p"], ...}
```
`summary_1p` 是 LLM 在 Canonicalize 阶段生成的摘要句，不是讲述者的原话。模型拿到"母亲护理了我"，就自己补了灶台、稀粥的场景。

**原因二：Writer 系统提示要求"具体场景"**

现有 `_WRITE_SYS`（第 456–468 行）明确要求：
> "每个叙事拍点至少包含一个具体场景（有时间/地点/人物/动作中的至少两项）"

当证据不够用时，模型为了满足这条规则，必然虚构。

**原因三：字数目标强制拉长，加剧虚构**

Planner 给每章设 6,000–10,000 字目标。当原话证据只够写 2,000 字，模型必须用虚构内容填满剩余 4,000–8,000 字。

### 1.3 现有代码结构（V2，执行人必读）

```
scripts/narrative_agent.py   986 行，6 个 agent 函数 + 1 个 orchestrator
scripts/batch_ingest.py      502 行，--narrative-only 入口

Agent 1: canonicalize_events()   → 1097 条 canonical events
Agent 2: resolve_timeline()      → 时间排序 + 人生阶段
Agent 3: plan_book()             → 章节计划 + story_bible
Agent 4: build_chapter_packet()  → 确定性，纯 Python，无 LLM
Agent 5: write_chapter()         → outline → prose（2次 LLM）
Agent 6: review_chapter() + rewrite_chapter()
```

Checkpoint 文件：`<name>.narr_ckpt.json`，包含 `canon`、`timeline`、`plan`、`story_bible`、`approved_chapters`

---

## 二、解决方案

### 2.1 核心策略

**不大改架构，只改"给 Writer 什么"和"Writer 被允许写什么"。**

三条硬规则：
1. Writer 只能使用提供的 `raw_quote` 和 `atomic_facts`，不得使用模型常识补充场景细节
2. 目标字数由证据量决定，不强制拉长
3. 审计器（Auditor）对输出做逐句检查，不通过则进入 Repair Agent 删除虚构句

### 2.2 架构对比

```
V2 架构：
  fragments → Canon → Timeline → Plan(固定字数) → Packet → Write(摘要输入) → Review

V3 架构：
  fragments + segments
      ↓
  Canon（升级：保留 raw_quote）
      ↓
  Timeline（不变）
      ↓
  Detail Bank（新增）← 从 raw_segments 提取原话细节库
      ↓
  Plan（升级：证据驱动字数）
      ↓
  Evidence Pack（升级：传 raw_quote + detail）
      ↓
  Grounded Writer（升级：禁止虚构列表 + 原话优先）
      ↓
  Auditor（新增：逐句事实检查）
      ↓
  Repair Agent（新增：只删不添）
      ↓
  Final Chapter
```

---

## 三、各模块技术规格

### 模块 A：升级 Canonicalize（Agent 1）

**文件：** `scripts/narrative_agent.py`，函数 `canonicalize_events()`

**改动：** 在每个 canonical event 中新增 `raw_quote` 和 `source_segment_texts` 字段。

**当前输出格式（V2）：**
```json
{
  "event_id": "evt-0001",
  "summary_1p": "我1938年出生在松江。",
  "quote_candidates": [{"text": "那时候日本人刚来", "fragment_id": "frag-uuid"}]
}
```

**目标输出格式（V3）：**
```json
{
  "event_id": "evt-0001",
  "summary_1p": "我1938年出生在松江。",
  "raw_quote": "我是1938年农历二月初一生的，那时候日本人来了，我妈妈正好怀着我，大着肚子",
  "source_segment_texts": [
    "我是1938年农历二月初一生的",
    "那时候就是日本人来了",
    "我妈妈呢正好怀着我，大着肚子"
  ],
  "quote_candidates": [{"text": "那时候日本人刚来", "fragment_id": "frag-uuid"}]
}
```

**实现方式：**
- Canon 阶段已有 `supporting_fragment_ids`，需要通过 fragment_id → fragment_text 查找原文
- `raw_quote`：取所有 supporting fragments 的 `fragment_text` 拼接（去重），截断到 300 字
- `source_segment_texts`：取每个 supporting fragment 对应的 `source_segment_ids` 里的 segment text（通过 pipeline.json 的 `segments` 列表查找），最多 5 条

**函数签名改变：**
```python
def canonicalize_events(
    fragments: list[dict],
    raw_segments: list[dict],   # ← 新增参数
    openrouter_key: str,
    batch_size: int = 80,
    canon_ckpt: dict | None = None,
    on_batch_save=None
) -> dict:
```

`raw_segments` 从 pipeline.json 的 `segments` 字段读取，已在 `generate_narrative_v2` 的入参中传入。

**验收：**
- 每个 canonical event 都有非空的 `raw_quote` 字段
- `raw_quote` 内容必须是讲述者原话（能在 pipeline.json segments 中找到），不是 LLM 生成的摘要

---

### 模块 B：新增 Detail Bank（新函数）

**文件：** `scripts/narrative_agent.py`，新增函数 `build_detail_bank()`

**作用：** 从 raw_segments 中提取适合直接引用的原话细节，按主题分类。这是 Writer 的"素材库"，Writer 只能用这里的内容写感官细节，不能自创。

**输入：** `raw_segments: list[dict]`（pipeline.json 的 segments 字段）

**输出格式：**
```json
{
  "details": [
    {
      "detail_id": "dtl-0001",
      "type": "verbatim_quote",
      "text": "脸上抹得漆黑漆黑的，把土都抹在脸上到处逃",
      "source_segment_id": "seg-uuid",
      "topics": ["战乱", "母亲", "逃难"]
    },
    {
      "detail_id": "dtl-0002",
      "type": "voice_marker",
      "text": "把我高兴得不得了",
      "source_segment_id": "seg-uuid",
      "topics": ["考试", "省女中"]
    },
    {
      "detail_id": "dtl-0003",
      "type": "uncertainty",
      "text": "我就太记不清了，好像是已经考上中学了",
      "source_segment_id": "seg-uuid",
      "topics": ["家庭", "考试"]
    }
  ]
}
```

**detail 类型：**
- `verbatim_quote`：可直接引用的生动原话（有具体行为/感官描写）
- `voice_marker`：体现讲述者口吻的短语（"把我高兴得不得了"、"那时候可苦了"）
- `uncertainty`：讲述者自己表达的不确定（"我记不清了"），用来替代模型瞎猜

**实现方式：** 纯 Python，无 LLM 调用。
- 遍历 segments，过滤 `speaker == "storyteller"` 的片段
- 筛选标准：`text` 长度 > 10 字，且包含以下任一特征：
  - 包含具体动词短语（逃、躲、哭、笑、跑、跳、抱）
  - 包含程度副词（特别、非常、可、那么、真是）
  - 包含"我记得"、"我还记得"、"那时候"
  - 包含情绪词（高兴、难过、害怕、着急）
- 对每条 detail 用简单关键词匹配分配 topics（基于 canonical events 的 life_stage 和 people/places 字段）

**验收：**
- 运行后生成 `detail_bank` dict，包含 ≥ 100 条 details（85岁_全集.pipeline.json 应产生约 300–500 条）
- 每条 detail 的 `text` 能在原始 segments 中找到

---

### 模块 C：升级 Plan（Agent 3）

**文件：** `scripts/narrative_agent.py`，函数 `plan_book()`

**改动：** 去掉固定字数目标，改为证据驱动的字数公式。

**当前行为：** 给 LLM 发 Plan 指令，LLM 返回每章 `target_chars: 6000/8000/10000`

**新行为：** Plan 阶段只决定章节划分和 slug/title，字数在 `build_chapter_packet()` 阶段由 Python 代码计算。

**字数计算公式（在 `build_chapter_packet()` 中实现）：**
```python
def _calc_target_chars(events: list[dict]) -> dict:
    p0_count = sum(1 for e in events if e.get("importance", 0) >= 0.9)
    p1_count = sum(1 for e in events if 0.6 <= e.get("importance", 0) < 0.9)
    evidence_score = p0_count * 3 + p1_count * 1

    if evidence_score <= 10:
        target = 400
    elif evidence_score <= 25:
        target = 400 + (evidence_score - 10) * 30   # 400–850
    elif evidence_score <= 60:
        target = 850 + (evidence_score - 25) * 15   # 850–1375
    else:
        target = min(1500, 1375 + (evidence_score - 60) * 5)

    return {
        "target_chars": target,
        "min_chars": max(200, target - 200),
        "max_chars": target + 300,
        "evidence_score": evidence_score,
    }
```

**验收：**
- 对于 85岁_全集：每章 `target_chars` 在 400–1500 字之间
- 没有任何章节的 `target_chars > 1500`（不允许强制拉长）
- Planner 的 LLM prompt 中不再出现固定数字（如 6000、8000、10000）

---

### 模块 D：升级 Evidence Pack（Agent 4）

**文件：** `scripts/narrative_agent.py`，函数 `build_chapter_packet()`

**改动：** 在 packet 中新增 `grounded_facts` 和 `allowed_details` 字段。

**当前 packet 结构（V2）：**
```json
{
  "slug": "childhood",
  "title": "松江的童年",
  "target_chars": 6000,
  "events": [...],             // event summaries
  "quote_candidates": [...],   // raw quotes (已有)
  "must_cover_event_ids": [...],
  "theme": "...",
  "opening_note": "...",
  "closing_note": "..."
}
```

**新增字段（V3）：**
```json
{
  "grounded_facts": [
    {
      "fact_id": "evt-0001",
      "claim": "我1938年农历二月初一出生在松江",
      "raw_quote": "我是1938年农历二月初一生的，那时候日本人来了",
      "people": ["母亲"],
      "places": ["松江"],
      "time": "1938年"
    }
  ],
  "allowed_details": [
    {
      "detail_id": "dtl-0001",
      "text": "脸上抹得漆黑漆黑的，把土都抹在脸上到处逃",
      "type": "verbatim_quote"
    }
  ],
  "forbidden_additions": [
    "未在 grounded_facts 中出现的天气、季节描述",
    "未在 grounded_facts 中出现的室内陈设（家具、器皿、食物）",
    "未在 grounded_facts 中出现的人物对话",
    "未在 grounded_facts 中出现的心理活动",
    "未在 grounded_facts 中出现的具体地点细节",
    "未在 allowed_details 中出现的感官描写"
  ]
}
```

**实现方式：**
- `grounded_facts`：从章节的 `events` 中提取，每个 event 取 `raw_quote` 字段（模块 A 新增）
- `allowed_details`：从 `detail_bank` 中按 topic 匹配（用章节的 life_stage、people、places 做关键词匹配），最多取 10 条

**验收：**
- 每个 packet 的 `grounded_facts` 字段非空
- `allowed_details` 里的每条 text 能在 pipeline.json 的 segments 中找到

---

### 模块 E：升级 Grounded Section Writer（Agent 5）

**文件：** `scripts/narrative_agent.py`，函数 `write_chapter()` + `_WRITE_SYS` + `_WRITE_USER`

**这是最重要的改动。**

**新 `_WRITE_SYS`（完整替换）：**
```
你是一位口述史整理员，帮助老人把口述录音整理成第一人称回忆录。

核心原则：真实性优先于文学性。每一句话都必须有证据支撑。

写作规则（严格遵守，不得违反）：
1. 全程第一人称「我」，不得出现第三人称"讲述者"、"她"、"他"（指代我自己时）。
2. 连续 prose（叙述性文字），不得出现列表、标题、项目符号。
3. 只能使用 grounded_facts 中的 claim 和 raw_quote 作为内容来源。
4. 只能使用 allowed_details 中的原话作为感官细节和氛围描写。
5. 【绝对禁止】不得添加 forbidden_additions 中列出的任何内容。
6. 如果证据不足以写到目标字数，宁可写短，不得虚构。
7. 可以对原话做轻微整理（去掉口头禅"呢"、"啊"、语气词），但不得改变意思。
8. 不确定的事情必须保留讲述者自己的不确定语气（"好像是"、"我记不清了"）。
```

**新 `_WRITE_USER` 中的关键变化：**

移除：`events_json`（包含 LLM 生成的 summary_1p）

新增：
```
可用事实（grounded_facts，只能使用这里的内容）：
{grounded_facts_json}

可用原话细节（allowed_details，感官描写只能从这里取）：
{allowed_details_json}

禁止添加的内容类型：
{forbidden_additions_json}

目标字数：{target_chars} 字（证据不足时可以写 {min_chars} 字，不得虚构凑字数）
```

**移除扩写调用（expand）：**

删除现有第 594–616 行的扩写逻辑（`if len(body) < min_acceptable: ...`）。

原因：扩写调用让模型在没有新证据的情况下继续生成，必然虚构。

**新的输出格式：**
```
{正文 prose}
===END===
used_fact_ids: evt-0001, evt-0003
used_detail_ids: dtl-0001, dtl-0005
```

Writer 函数解析 `used_fact_ids` 和 `used_detail_ids`，存入 draft。

**验收：**
- 输出正文中不出现 forbidden_additions 中的类型（由 Auditor 检查，见模块 F）
- 输出正文字数 ≥ min_chars，或标注 `insufficient_evidence: true`
- 不再有 "expanding..." 日志

---

### 模块 F：新增 Atomic Claim Auditor（新函数）

**文件：** `scripts/narrative_agent.py`，新增函数 `audit_chapter()`

**作用：** 对 Writer 输出的每句话做事实检查，判断是否有证据支撑。

**触发时机：** 在 `review_chapter()` 之前调用，替换现有的 coverage hard check。

**实现方式（基于 StorySage 论文 Appendix B.5 的方法）：**

```python
_AUDIT_SYS = """
你是一位口述史事实审计员。你的任务是判断回忆录正文中每一句话是否有原始证据支撑。

步骤：
1. 把"可用事实"拆成原子信息单元（每条事实的最小可验证成分）
2. 把正文拆成原子 claim（每句话的核心断言）
3. 对每条 claim 判断：supported（有证据）/ unsupported（无证据）/ inferred（合理推断，非关键细节）
4. 输出结果

"inferred" 仅用于逻辑连接词、时间过渡等非实质内容（"后来"、"因此"、"那时"）。
所有实质性内容（人物行为、地点、事件、感官细节）必须是 supported 或标注 unsupported。

输出必须是合法 JSON。
"""

_AUDIT_USER = """
可用事实（source of truth）：
{grounded_facts_json}

可用原话细节：
{allowed_details_json}

正文：
{body}

输出格式：
{
  "atomic_units": ["我1938年出生在松江", "母亲正怀着我", ...],
  "claims": [
    {
      "sentence": "1938年农历二月初一，我出生在松江。",
      "claim": "我1938年农历二月初一出生在松江",
      "status": "supported",
      "support_ids": ["evt-0001"]
    },
    {
      "sentence": "那间土房进门就是灶台。",
      "claim": "土房里有灶台",
      "status": "unsupported",
      "support_ids": []
    }
  ],
  "summary": {
    "total_claims": 12,
    "supported": 9,
    "unsupported": 2,
    "inferred": 1
  }
}
"""
```

**Auditor 判定规则（Python 代码，在 `audit_chapter()` 函数中）：**
```python
def audit_chapter(draft: dict, packet: dict) -> dict:
    # LLM call: get per-claim verdicts
    ...
    claims = result["claims"]
    unsupported = [c for c in claims if c["status"] == "unsupported"]
    verdict = "pass" if len(unsupported) == 0 else "fail"
    return {
        "verdict": verdict,
        "claims": claims,
        "unsupported_sentences": [c["sentence"] for c in unsupported],
        "unsupported_count": len(unsupported),
    }
```

**验收：**
- 对 V2 已生成的章节运行 Auditor，应能识别出已知虚构句（如"灶台"、"稀粥"）
- 对 V3 生成的章节运行 Auditor，unsupported_count 应为 0

---

### 模块 G：新增 Repair Agent（新函数）

**文件：** `scripts/narrative_agent.py`，新增函数 `repair_chapter()`

**作用：** 删除 Auditor 标记为 unsupported 的句子，不添加任何新内容。

**触发条件：** `audit_result["verdict"] == "fail"`

**实现方式：**

```python
_REPAIR_SYS = """
你是一位口述史编辑。你的任务是从回忆录正文中删除没有证据支撑的句子。

规则（严格遵守）：
1. 只删除，不添加任何新内容。
2. 不改写保留的句子（保留句字句不变）。
3. 删除后确保上下文连贯（如果删除导致段落断裂，可删除整段，不得用新内容填补）。
4. 输出纯中文正文，不加任何说明。
"""

_REPAIR_USER = """
原稿：
{body}

需要删除的句子（逐字匹配）：
{unsupported_sentences_json}

请输出删除后的正文：
"""
```

**验收：**
- Repair 输出的字数 ≤ Writer 输出的字数
- Repair 输出中不包含任何 `unsupported_sentences` 中的内容
- Repair 后再次运行 Auditor，`unsupported_count` 应为 0

---

### 模块 H：更新 Orchestrator

**文件：** `scripts/narrative_agent.py`，函数 `generate_narrative_v2()`（重命名为 `generate_narrative_v3()`）

**新流程（每章）：**

```python
# 旧流程（V2）：
packet = build_chapter_packet(ch_spec, story_bible, ordered_events)
draft = write_chapter(packet, story_bible, prev_ending, openrouter_key)
review = review_chapter(draft, packet, story_bible, approved, openrouter_key)
if hard_fails: draft = rewrite_chapter(...)

# 新流程（V3）：
packet = build_chapter_packet(ch_spec, story_bible, ordered_events, detail_bank)  # 传入 detail_bank
draft = write_chapter(packet, story_bible, prev_ending, openrouter_key)
audit = audit_chapter(draft, packet, openrouter_key)
if audit["verdict"] == "fail":
    draft = repair_chapter(draft, audit, openrouter_key)
    audit2 = audit_chapter(draft, packet, openrouter_key)
    # 不论 audit2 结果如何，commit（repair 后不再 rewrite）
review = review_chapter(draft, packet, story_bible, approved, openrouter_key)
# review 只检查 pov（第一人称）和 style（叙事质量），不再检查 length/coverage
```

**保留 checkpoint 机制**（`narr_ckpt.json`），新增 `detail_bank` 字段存入 checkpoint。

**新的 main() 入口支持：**
```bash
python -m scripts.narrative_agent <pipeline.json> [--ckpt <ckpt.json>]
```

---

## 四、数据格式规范

### 4.1 完整 V3 chapter draft 结构

```json
{
  "slug": "childhood",
  "title": "松江的童年",
  "body": "...",
  "used_fact_ids": ["evt-0001", "evt-0003"],
  "used_detail_ids": ["dtl-0001"],
  "target_chars": 600,
  "actual_chars": 587,
  "insufficient_evidence": false,
  "audit": {
    "verdict": "pass",
    "unsupported_count": 0,
    "claims": [...]
  }
}
```

### 4.2 pipeline.json 新增字段

```json
{
  "audio_file": "...",
  "segments": [...],
  "claims": [...],
  "narrative": {
    "version": "v3",
    "chapters": [...],
    "detail_bank_size": 342
  }
}
```

---

## 五、验收标准

### 5.1 功能验收（必须全部通过）

| 编号 | 验收项 | 检查方法 |
|---|---|---|
| F1 | 每个 canonical event 有非空 `raw_quote` 字段 | `python -c "import json; d=json.load(open('x.narr_ckpt.json')); assert all(e.get('raw_quote') for e in d['canon']['canonical_events'])"` |
| F2 | detail_bank 包含 ≥ 100 条 details | 运行后打印 `detail_bank_size` |
| F3 | 每章 `target_chars` ≤ 1500 | 检查 chapter plan 中无 >1500 的值 |
| F4 | Writer 输出中不包含 "expanding..." 日志 | grep 输出日志 |
| F5 | Auditor 对 V3 输出的 `unsupported_count` 为 0 | 每章 audit 结果打印 |
| F6 | Repair Agent 输出字数 ≤ Writer 输出字数 | 检查日志中的字数变化 |
| F7 | 最终正文不包含 forbidden_additions 中的类型 | 人工抽查 2 章，逐句对照原始 segments |

### 5.2 质量验收（人工检查）

取最终输出的任意一章，从头读到尾，对每一句话做以下判断：

1. **这句话在 pipeline.json 的 segments 中能找到原始依据吗？**（字面匹配或语义对应）
2. **如果找不到，是逻辑连接词（"后来"、"那时候"）还是实质内容（室内描写、天气、对话）？**

**通过标准：** 实质内容 100% 可追溯，不通过项为 0。

### 5.3 回归验收

确保以下现有功能未被破坏：
- `--narrative-only` 参数仍然有效（`batch_ingest.py` 第 431 行）
- Checkpoint 恢复仍然有效（删掉 `approved_chapters`，重跑，Stage 1–3 不重复执行）
- 输出仍然写入 `pipeline.json` 的 `narrative` 字段

---

## 六、不在本次范围内（明确边界）

以下内容**不做**，防止跑偏：

| 不做的事 | 原因 |
|---|---|
| 不改 ASR 流程 | batch_ingest.py 的 ASR、diarization、fragment 提取部分不动 |
| 不换模型 | 继续用 deepseek/deepseek-chat，模型切换是独立决策 |
| 不做多轮采访/Interviewer Agent | 当前只处理已有音频，无实时采访场景 |
| 不做 UI/API 对接 | 只改 scripts/narrative_agent.py，输出格式兼容 |
| 不重写 Timeline/Plan LLM prompt | 问题出在 Writer，不在这两个 Agent |
| 不处理 entity_registry | 不做人名/地名跨章一致性检查（留后续） |
| 不做 Session Coordinator | 无后续采访场景 |

---

## 七、执行顺序和工作量估计

| 步骤 | 模块 | 预计工时 | 依赖 |
|---|---|---|---|
| 1 | 升级 Canonicalize（模块 A） | 2h | 无 |
| 2 | 实现 Detail Bank（模块 B） | 2h | 无 |
| 3 | 升级 Plan 字数公式（模块 C） | 1h | 无 |
| 4 | 升级 Evidence Pack（模块 D） | 1h | A、B |
| 5 | 升级 Grounded Writer（模块 E） | 3h | D |
| 6 | 实现 Auditor（模块 F） | 2h | E |
| 7 | 实现 Repair Agent（模块 G） | 1h | F |
| 8 | 更新 Orchestrator（模块 H） | 2h | A–G |
| 9 | 端到端测试 + 验收 | 2h | A–H |
| **合计** | | **~16h** | |

步骤 1、2、3 可并行。步骤 4 依赖 1 和 2，需串行。其余串行执行。

---

## 八、测试命令

**开发阶段（只测 Writer，跳过 Stage 1–3）：**
```bash
# 复用现有 checkpoint 的 Stage 1–3，只重跑 Stage 4–8
# 删除 checkpoint 中的 approved_chapters，保留 canon/timeline/plan/story_bible
python -c "
import json; p=open('scripts/test_audio/85岁_全集.pipeline.narr_ckpt.json')
d=json.load(p); d.pop('approved_chapters', None); 
open('scripts/test_audio/85岁_全集.pipeline.narr_ckpt.json','w').write(json.dumps(d,ensure_ascii=False))
"
.venv/bin/python -m scripts.narrative_agent \
  scripts/test_audio/85岁_全集.pipeline.json \
  > /tmp/narrative_v3.log 2>&1 &
tail -f /tmp/narrative_v3.log
```

**验收检查脚本：**
```bash
python -c "
import json
d = json.load(open('scripts/test_audio/85岁_全集.pipeline.json'))
chapters = d['narrative']['chapters']
print(f'Chapters: {len(chapters)}')
for c in chapters:
    audit = c.get('audit', {})
    print(f'  [{c[\"slug\"]}] {len(c[\"body\"])} chars | audit: {audit.get(\"verdict\",\"?\")}, unsupported={audit.get(\"unsupported_count\",\"?\")}')
"
```

---

## 附录：关键文件索引

| 文件 | 用途 | 本次是否修改 |
|---|---|---|
| `scripts/narrative_agent.py` | 主要修改文件 | ✅ 大改 |
| `scripts/batch_ingest.py` | 入口文件，`--narrative-only` | 只改 `generate_narrative_v2` → `v3` 的调用，其余不动 |
| `scripts/test_audio/85岁_全集.pipeline.json` | 测试数据 | 只读（输出会覆盖 narrative 字段） |
| `scripts/test_audio/85岁_全集.pipeline.narr_ckpt.json` | Checkpoint | 自动更新，人工操作时只删 approved_chapters |
| `api_key` | OpenRouter key | 不动 |
