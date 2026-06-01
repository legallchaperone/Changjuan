#!/usr/bin/env python3
"""
长卷 Narrative Agent v3 — 分层、证据驱动、逐章写作流水线

Agents:
  1. canonicalize  — merge/deduplicate fragments → canonical events
  2. timeline      — order events chronologically
  3. plan          — design chapter structure + story_bible_v0
  4. packet        — build evidence packet for one chapter (deterministic)
  5. write         — micro-outline → chapter prose (2 LLM calls)
  6. audit/repair  — sentence-level grounding check → delete unsupported sentences
  7. polish        — prose style improvement; re-audited, reverts if fabrication detected
  8. review        — POV/style quality check

Orchestrator runs 1-4 once, then loops 5-8 per chapter.
"""

import argparse
import json
import re
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
KEYS_FILE = ROOT / "api_key"

# ── Helpers ────────────────────────────────────────────────────────────────────

def load_openrouter_key() -> str:
    return KEYS_FILE.read_text().strip().splitlines()[0].strip()


def _llm(client, messages: list[dict], *, json_mode: bool = True,
         max_tokens: int = 4096, temperature: float = 0.2) -> str:
    """Single LLM call with retry on rate-limit and connection errors."""
    import httpx
    kwargs = dict(
        model="deepseek/deepseek-chat",
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=300,  # 5-minute hard cap per call
    )
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    for attempt in range(5):
        try:
            resp = client.chat.completions.create(**kwargs)
            content = resp.choices[0].message.content if resp.choices else None
            if content:
                return content
            finish = resp.choices[0].finish_reason if resp.choices else "no choices"
            raise RuntimeError(f"Empty LLM response, finish_reason={finish}")
        except Exception as e:
            is_429 = "429" in str(e)
            is_conn = any(k in str(type(e)) for k in ("ConnectError", "APIConnectionError",
                          "ReadTimeout", "TimeoutError")) \
                      or "EOF" in str(e) or "Connection error" in str(e) \
                      or "timed out" in str(e).lower() \
                      or isinstance(e, (json.JSONDecodeError, httpx.TimeoutException))
            if (is_429 or is_conn) and attempt < 4:
                wait = 30 * (2 ** attempt) if is_429 else 15 * (attempt + 1)
                label = "rate-limited" if is_429 else "timeout/connection error"
                print(f"    ↺ {label}, retry {attempt+1}/5 in {wait}s ...", flush=True)
                time.sleep(wait)
            else:
                raise


def _text_value(item: dict, *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _dedupe_keep_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = value.strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
    return result


def _segment_index(raw_segments: list[dict]) -> dict[str, dict]:
    return {
        str(seg_id): segment
        for segment in raw_segments
        if (seg_id := segment.get("id") or segment.get("segment_id"))
    }


def _fragment_index(fragments: list[dict]) -> dict[str, dict]:
    return {
        str(frag_id): fragment
        for fragment in fragments
        if (frag_id := fragment.get("id") or fragment.get("fragment_id"))
    }


def _event_supporting_fragment_ids(event: dict) -> list[str]:
    ids = [str(fid) for fid in event.get("supporting_fragment_ids", []) if fid]
    if ids:
        return _dedupe_keep_order(ids)
    quote_fragment_ids = [
        str(candidate["fragment_id"])
        for candidate in event.get("quote_candidates", [])
        if isinstance(candidate, dict) and candidate.get("fragment_id")
    ]
    return _dedupe_keep_order(quote_fragment_ids)


def _attach_event_sources(
    events: list[dict],
    fragments: list[dict],
    raw_segments: list[dict],
) -> list[dict]:
    fragments_by_id = _fragment_index(fragments)
    segments_by_id = _segment_index(raw_segments)

    for event in events:
        supporting_ids = _event_supporting_fragment_ids(event)
        source_fragments = [fragments_by_id[fid] for fid in supporting_ids if fid in fragments_by_id]

        raw_quote_parts = _dedupe_keep_order(
            [_text_value(fragment, "fragment_text", "text") for fragment in source_fragments]
        )
        if raw_quote_parts:
            event["raw_quote"] = " ".join(raw_quote_parts)[:300]
        else:
            event.setdefault("raw_quote", "")

        segment_ids: list[str] = []
        for fragment in source_fragments:
            segment_ids.extend(str(seg_id) for seg_id in fragment.get("source_segment_ids", []) if seg_id)
        segment_texts = _dedupe_keep_order(
            [
                _text_value(segments_by_id[seg_id], "text", "segment_text", "transcript")
                for seg_id in segment_ids
                if seg_id in segments_by_id
            ]
        )
        event["source_segment_texts"] = segment_texts[:5]

    return events


def _estimate_max_tokens(facts: list[dict]) -> int:
    """Estimate a safe max_tokens ceiling based on evidence count.
    ~50 chars per fact, ~1.8 chars per token, plus headroom. Cap at 12000.
    """
    return min(12000, int(len(facts) * 50 / 1.8) + 500)


def _time_label(time_span: dict | str | None) -> str:
    if not time_span:
        return ""
    if isinstance(time_span, str):
        return time_span
    start = str(time_span.get("start") or "").strip()
    end = str(time_span.get("end") or "").strip()
    if start and end and start != end:
        return f"{start}–{end}"
    return start or end


def _detail_topics(text: str) -> list[str]:
    topic_keywords = {
        "战乱": ["日本", "枪", "逃", "躲", "土", "战", "解放", "逃难"],
        "母亲": ["母亲", "妈妈", "我妈", "娘"],
        "父亲": ["父亲", "爸爸", "我爸", "爹"],
        "求学": ["学校", "中学", "大学", "老师", "读书", "上学", "考试", "省女中"],
        "考试": ["考试", "考上", "录取", "成绩"],
        "工作": ["工作", "单位", "团省委", "供销社", "上班"],
        "家庭": ["家里", "妹妹", "弟弟", "姐姐", "哥哥", "外婆", "祖母", "奶奶"],
        "松江": ["松江"],
        "上海": ["上海"],
    }
    topics: list[str] = []
    for topic, keywords in topic_keywords.items():
        if any(keyword in text for keyword in keywords):
            topics.append(topic)
    if "那时候" in text or "小时候" in text:
        topics.append("童年")
    return _dedupe_keep_order(topics)


def _detail_type(text: str) -> str:
    if any(marker in text for marker in ("记不清", "不记得", "好像", "大概", "可能")):
        return "uncertainty"
    voice_markers = ("不得了", "可", "真是", "那时候", "特别", "非常", "太")
    action_markers = ("逃", "躲", "哭", "笑", "跑", "跳", "抱", "抹", "捂", "背", "走")
    if any(marker in text for marker in action_markers):
        return "verbatim_quote"
    if any(marker in text for marker in voice_markers):
        return "voice_marker"
    return "verbatim_quote"


def build_detail_bank(raw_segments: list[dict]) -> dict:
    details: list[dict] = []
    feature_markers = (
        "逃", "躲", "哭", "笑", "跑", "跳", "抱", "抹", "捂", "背", "走",
        "特别", "非常", "可", "那么", "真是", "太", "我记得", "我还记得",
        "那时候", "高兴", "难过", "害怕", "着急", "记不清", "好像",
    )

    for segment in raw_segments:
        speaker = segment.get("speaker")
        if speaker and speaker != "storyteller":
            continue
        text = _text_value(segment, "text", "segment_text", "transcript")
        if len(text) <= 10:
            continue
        if not any(marker in text for marker in feature_markers):
            continue
        detail = {
            "detail_id": f"dtl-{len(details) + 1:04d}",
            "type": _detail_type(text),
            "text": text,
            "source_segment_id": segment.get("id") or segment.get("segment_id") or "",
            "topics": _detail_topics(text),
        }
        details.append(detail)

    return {"details": details}


# ── Agent 1: Canonicalize ──────────────────────────────────────────────────────

_CANON_SYS = """\
你是一位口述史整理员。你的任务是把一批记忆片段（来自同一位讲述者的采访转写）
归并成规范事件（canonical events）。

规则：
1. 把描述同一事件的多个片段合并为一个 canonical_event。
2. 统一人名称谓（例如"我妈""妈妈""母亲"→ canonical "母亲"）。
3. 统一地名（松江县 / 松江 → canonical "松江"）。
4. 如果同一事件的两个片段在年份/地点/顺序上互相矛盾，把矛盾登记进 conflicts。
5. 从片段里挑出最生动的原话候选（quote_candidates）。
6. importance 评分：P0 事件且有具体年份/地点/人名 = 0.9–1.0；P1 = 0.6–0.89；P2 = 0.1–0.59。

输出必须是合法 JSON，不加任何额外说明。
"""

_CANON_USER = """\
请把以下 {n} 个记忆片段整理成 canonical events。

{fragments_json}

输出格式：
{{
  "canonical_events": [
    {{
      "event_id": "evt-001",
      "summary_1p": "我1938年出生在松江。",
      "time_span": {{"start": "1938", "end": "1938", "granularity": "year"}},
      "life_stage": "童年",
      "people": ["母亲"],
      "places": ["松江"],
      "supporting_fragment_ids": ["frag-uuid-1"],
      "conflicts": [],
      "quote_candidates": [{{"text": "那时候日本人刚来", "fragment_id": "frag-uuid-1"}}],
      "importance": 0.95
    }}
  ],
  "name_normalizations": [{{"raw": "我妈", "canonical": "母亲"}}],
  "place_normalizations": [],
  "conflicts": []
}}
"""


def canonicalize_events(fragments: list[dict],
                        raw_segments: list[dict] | str | None,
                        openrouter_key: str | None = None,
                        batch_size: int = 80,
                        canon_ckpt: dict | None = None,
                        on_batch_save=None) -> dict:
    if openrouter_key is None:
        openrouter_key = str(raw_segments or "")
        raw_segments = []
    raw_segments = raw_segments if isinstance(raw_segments, list) else []

    from openai import OpenAI
    client = OpenAI(api_key=openrouter_key, base_url="https://openrouter.ai/api/v1")

    all_events: list[dict] = canon_ckpt.get("canonical_events", []) if canon_ckpt else []
    name_norm: list[dict] = canon_ckpt.get("name_normalizations", []) if canon_ckpt else []
    place_norm: list[dict] = canon_ckpt.get("place_normalizations", []) if canon_ckpt else []
    all_conflicts: list[dict] = canon_ckpt.get("conflicts", []) if canon_ckpt else []
    start_batch: int = canon_ckpt.get("_next_batch", 0) if canon_ckpt else 0

    batches = [fragments[i:i+batch_size] for i in range(0, len(fragments), batch_size)]
    print(f"[Canon] {len(fragments)} fragments → {len(batches)} batches "
          f"(resuming from {start_batch})", flush=True)

    for idx, batch in enumerate(batches):
        if idx < start_batch:
            continue
        print(f"[Canon] Batch {idx+1}/{len(batches)} ({len(batch)} frags) ...", flush=True)
        minimal = [
            {"id": f["id"], "text": f["fragment_text"],
             "type": f.get("fragment_type", ""), "priority": f.get("fragment_priority", "")}
            for f in batch
        ]
        raw = _llm(client, [
            {"role": "system", "content": _CANON_SYS},
            {"role": "user", "content": _CANON_USER.format(
                n=len(batch), fragments_json=json.dumps(minimal, ensure_ascii=False)
            )},
        ], max_tokens=16384)

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            print(f"  [Canon] Batch {idx+1} JSON truncated — skipping, will lose ~{len(batch)} frags", flush=True)
            parsed = {}
        batch_events = _attach_event_sources(
            parsed.get("canonical_events", []),
            fragments,
            raw_segments,
        )
        all_events.extend(batch_events)
        name_norm.extend(parsed.get("name_normalizations", []))
        place_norm.extend(parsed.get("place_normalizations", []))
        all_conflicts.extend(parsed.get("conflicts", []))
        # Update in-progress canon_ckpt (mutable dict passed by reference)
        if canon_ckpt is not None:
            canon_ckpt.update({
                "canonical_events": all_events,
                "name_normalizations": name_norm,
                "place_normalizations": place_norm,
                "conflicts": all_conflicts,
                "_next_batch": idx + 1,
            })
            if on_batch_save:
                on_batch_save()

    # Re-index event IDs to be globally unique
    for i, ev in enumerate(all_events):
        ev["event_id"] = f"evt-{i+1:04d}"
    _attach_event_sources(all_events, fragments, raw_segments)

    print(f"[Canon] Done — {len(all_events)} canonical events", flush=True)
    return {
        "canonical_events": all_events,
        "name_normalizations": name_norm,
        "place_normalizations": place_norm,
        "conflicts": all_conflicts,
    }


# ── Agent 2: Timeline ──────────────────────────────────────────────────────────

_TIMELINE_SYS = """\
你是一位口述史时间线整理员。你的任务是把散乱的 canonical events 按照讲述者的
人生时间顺序排列，并划分人生阶段。

规则：
1. 按照 time_span.start 排序；时间不确定的，根据人生逻辑推断大致位置。
2. 划分人生阶段（例如：童年、求学、青年工作、成家立业、晚年）。
3. 标记时间不确定的事件（uncertain_edges）。
4. 输出必须是合法 JSON。
"""

_TIMELINE_USER = """\
请把以下 canonical events 按时间排序并划分人生阶段。

{events_json}

输出格式：
{{
  "ordered_event_ids": ["evt-0001", "evt-0003", ...],
  "life_stages": [
    {{
      "stage": "童年",
      "approx_years": "1938–1949",
      "event_ids": ["evt-0001", "evt-0002"]
    }}
  ],
  "uncertain_edges": [
    {{"event_ids": ["evt-0020", "evt-0021"], "reason": "讲述者说过两次但年份不同"}}
  ]
}}
"""


def resolve_timeline(canon: dict, openrouter_key: str) -> dict:
    from openai import OpenAI
    client = OpenAI(api_key=openrouter_key, base_url="https://openrouter.ai/api/v1")

    events = canon["canonical_events"]
    # Send compact summary (just id, summary, time_span, life_stage, importance)
    compact = [
        {"id": ev["event_id"], "summary": ev["summary_1p"],
         "time": ev.get("time_span", {}), "stage": ev.get("life_stage", ""),
         "importance": ev.get("importance", 0.5)}
        for ev in events
    ]
    print(f"[Timeline] Ordering {len(compact)} events ...", flush=True)

    raw = _llm(client, [
        {"role": "system", "content": _TIMELINE_SYS},
        {"role": "user", "content": _TIMELINE_USER.format(
            events_json=json.dumps(compact, ensure_ascii=False)
        )},
    ], max_tokens=4096)

    result = json.loads(raw)
    # Build ordered event list for downstream use
    ev_index = {ev["event_id"]: ev for ev in events}
    ordered = [ev_index[eid] for eid in result.get("ordered_event_ids", [])
               if eid in ev_index]
    # Append any events not mentioned in ordering (shouldn't happen but be safe)
    mentioned = set(result.get("ordered_event_ids", []))
    ordered += [ev for ev in events if ev["event_id"] not in mentioned]

    print(f"[Timeline] Done — {len(result.get('life_stages', []))} life stages", flush=True)
    return {
        "ordered_events": ordered,
        "life_stages": result.get("life_stages", []),
        "uncertain_edges": result.get("uncertain_edges", []),
    }


# ── Agent 3: Plan Book ─────────────────────────────────────────────────────────

_PLAN_SYS = """\
你是一位回忆录编辑。你的任务是根据已排序的人生事件，规划回忆录的章节结构，
并建立 story bible（全书的人名、称谓、风格约束）。

规则：
1. 章节数由内容决定：事件集中、主题连贯的可合并；跨度大、主题明显转变的应拆开。
   不要预设章节数，按材料的自然分段来。
2. 参考每个人生阶段的事件数（stages_json 里有 event_count）：
   - 一个阶段事件很少（<15）：可与相邻阶段合并为一章
   - 一个阶段事件适中（15–40）：通常一章
   - 一个阶段事件较多（>40）：考虑按内容主题拆成 2–3 章，让每章聚焦
3. 拆分的依据是内容主题，不是硬性数字——如果 50 个事件主题高度连贯，一章也可以。
4. 每章要有明确的事件覆盖范围（must_cover_event_ids）。
5. story bible 记录：人名/称谓规范、地名规范、风格要求、已知时间锚点。
6. 不要给章节设定 target_chars，字数由内容自然决定。
7. 输出必须是合法 JSON。
"""

_PLAN_USER = """\
以下是讲述者的人生事件，已按时间排序，并划分了人生阶段。
请规划章节结构并建立 story bible。

人生阶段：
{stages_json}

全部事件（按顺序，共 {n} 条）：
{events_json}

输出格式：
{{
  "chapter_plan": [
    {{
      "slug": "childhood",
      "title": "松江的童年",
      "theme": "出生、家庭、战乱中的成长",
      "must_cover_event_ids": ["evt-0001", "evt-0002"],
      "suggested_event_ids": ["evt-0003"],
      "opening_note": "从出生或最早记忆切入",
      "closing_note": "以某个转折或离开结束"
    }}
  ],
  "story_bible": {{
    "narrator_birth_approx": "1938",
    "narrator_birth_place": "松江",
    "name_map": [{{"canonical": "母亲", "aliases": ["我妈", "妈妈"]}}],
    "place_map": [{{"canonical": "松江", "aliases": ["松江县"]}}],
    "timeline_anchors": [{{"year": "1949", "event": "上海解放"}}],
    "style_profile": {{
      "register": "朴素、温厚、第一人称回忆录",
      "keep": ["老一辈称谓", "时代说法", "地域词"],
      "avoid": ["总结腔", "空泛感悟", "记者语气"]
    }},
    "chapter_synopses": []
  }}
}}
"""


def plan_book(timeline: dict, openrouter_key: str) -> tuple[list[dict], dict]:
    from openai import OpenAI
    client = OpenAI(api_key=openrouter_key, base_url="https://openrouter.ai/api/v1")

    events = timeline["ordered_events"]
    stages = timeline["life_stages"]

    # Compact event list for planning (just what's needed to decide structure)
    compact_events = [
        {"id": ev["event_id"], "summary": ev["summary_1p"],
         "stage": ev.get("life_stage", ""), "importance": ev.get("importance", 0.5)}
        for ev in events
    ]

    # Add event_count to each stage so Planner can see density
    stages_with_counts = [
        {**s, "event_count": len(s.get("event_ids", []))}
        for s in stages
    ]

    print(f"[Plan] Planning book from {len(events)} events ...", flush=True)

    raw = _llm(client, [
        {"role": "system", "content": _PLAN_SYS},
        {"role": "user", "content": _PLAN_USER.format(
            stages_json=json.dumps(stages_with_counts, ensure_ascii=False),
            n=len(compact_events),
            events_json=json.dumps(compact_events, ensure_ascii=False),
        )},
    ], max_tokens=6144)

    result = json.loads(raw)
    chapter_plan = result.get("chapter_plan", [])
    story_bible = result.get("story_bible", {})
    story_bible.setdefault("chapter_synopses", [])

    print(f"[Plan] Done — {len(chapter_plan)} chapters planned", flush=True)
    for ch in chapter_plan:
        print(f"  [{ch['slug']}] {ch['title']} — "
              f"{len(ch.get('must_cover_event_ids', []))} must-cover events", flush=True)
    return chapter_plan, story_bible


# ── Agent 4: Build Chapter Packet (deterministic) ─────────────────────────────

def build_chapter_packet(chapter_spec: dict, story_bible: dict,
                         ordered_events: list[dict],
                         detail_bank: dict | None = None) -> dict:
    """
    Select events and quotes for a chapter. Purely deterministic — no LLM.
    Returns a packet with all the evidence the writing agent needs.
    """
    must_id_list = [eid for eid in chapter_spec.get("must_cover_event_ids", []) if eid]
    sugg_id_list = [eid for eid in chapter_spec.get("suggested_event_ids", []) if eid]
    must_ids = set(must_id_list)
    sugg_ids = set(sugg_id_list)

    ev_index = {ev["event_id"]: ev for ev in ordered_events}

    must_events = [ev_index[eid] for eid in must_id_list if eid in ev_index]
    sugg_events = [ev_index[eid] for eid in sugg_id_list if eid in ev_index]

    # Also include high-importance events in the same life stage
    stage_events = [
        ev for ev in ordered_events
        if ev.get("life_stage") in [e.get("life_stage") for e in must_events]
        and ev["event_id"] not in must_ids | sugg_ids
        and ev.get("importance", 0) >= 0.7
    ][:10]  # cap at 10 bonus events

    all_events = []
    seen_event_ids: set[str] = set()
    for event in must_events + sugg_events + stage_events:
        event_id = event["event_id"]
        if event_id not in seen_event_ids:
            seen_event_ids.add(event_id)
            all_events.append(event)

    # Collect quote candidates
    quotes = []
    for ev in all_events:
        quotes.extend(ev.get("quote_candidates", []))
    quotes = quotes[:8]  # top 8 quotes

    grounded_facts = [
        {
            "fact_id": ev["event_id"],
            "claim": ev.get("summary_1p", ""),
            "raw_quote": ev.get("raw_quote", ""),
            "people": ev.get("people", []),
            "places": ev.get("places", []),
            "time": _time_label(ev.get("time_span")),
        }
        for ev in all_events
    ]

    context_terms: list[str] = []
    for key in ("title", "theme", "opening_note", "closing_note"):
        context_terms.append(str(chapter_spec.get(key, "")))
    for event in all_events:
        context_terms.extend(str(value) for value in event.get("people", []))
        context_terms.extend(str(value) for value in event.get("places", []))
        context_terms.append(str(event.get("life_stage", "")))
        context_terms.append(str(event.get("summary_1p", "")))
    context_text = " ".join(term for term in context_terms if term)
    allowed_details = []
    for detail in (detail_bank or {}).get("details", []):
        topics = detail.get("topics", [])
        if topics and not any(str(topic) and str(topic) in context_text for topic in topics):
            continue
        allowed_details.append({
            "detail_id": detail.get("detail_id", ""),
            "text": detail.get("text", ""),
            "type": detail.get("type", ""),
            "source_segment_id": detail.get("source_segment_id", ""),
        })
        if len(allowed_details) >= 10:
            break

    forbidden_additions = [
        "未在 grounded_facts 中出现的天气、季节描述",
        "未在 grounded_facts 中出现的室内陈设（家具、器皿、食物）",
        "未在 grounded_facts 中出现的人物对话",
        "未在 grounded_facts 中出现的心理活动",
        "未在 grounded_facts 中出现的具体地点细节",
        "未在 allowed_details 中出现的感官描写",
    ]

    return {
        "slug": chapter_spec["slug"],
        "title": chapter_spec["title"],
        "theme": chapter_spec.get("theme", ""),
        "opening_note": chapter_spec.get("opening_note", ""),
        "closing_note": chapter_spec.get("closing_note", ""),
        "must_cover_event_ids": must_id_list,
        "events": all_events,
        "quote_candidates": quotes,
        "grounded_facts": grounded_facts,
        "allowed_details": allowed_details,
        "forbidden_additions": forbidden_additions,
    }


# ── Agent 5: Write Chapter ─────────────────────────────────────────────────────

_OUTLINE_SYS = """\
你是一位回忆录写作规划师。你的任务是为当前章节制定微纲（写作节拍）。

规则：
1. 把章节拆成 3–6 个叙事拍点（beats），按时间或主题分组。
2. 每个拍点列出：简短描述、涉及的事件ID列表、建议引用的原话。
3. 所有 grounded_facts 都必须分配到某个 beat，不得遗漏。
4. 拍点之间要有自然过渡。
5. 不设字数目标，字数由内容自然决定。
6. 输出必须是合法 JSON。
"""

_OUTLINE_USER = """\
请为以下章节制定微纲。

章节标题：{title}
章节主题：{theme}
开篇建议：{opening_note}
结尾建议：{closing_note}

本章所有可用事件（必须全部分配到 beats）：
{all_facts_json}

可用原话候选：
{quotes_json}

Story Bible（人名/称谓/风格约束）：
{bible_json}

输出格式：
{{
  "beats": [
    {{
      "beat_id": 1,
      "description": "从出生的背景切入，提及战乱年代",
      "event_ids": ["evt-0001", "evt-0002"],
      "suggested_quotes": ["那时候日本人刚来"]
    }},
    {{
      "beat_id": 2,
      "description": "祖母启蒙识字，早慧的童年",
      "event_ids": ["evt-0003"],
      "suggested_quotes": []
    }}
  ]
}}
"""

_WRITE_SYS = """\
你是一位口述史整理员，帮助老人把口述录音整理成第一人称回忆录。

核心原则：真实性优先于文学性。每一句话都必须有证据支撑。

写作规则（严格遵守）：
1. 全程第一人称「我」，不得出现第三人称"讲述者"、"她"、"他"（指代我自己时）。
2. 连续 prose（叙述性文字），不得出现列表、标题、项目符号。
3. 只能使用 grounded_facts 中的 claim 和 raw_quote 作为内容来源。
4. 只能使用 allowed_details 中的原话作为感官细节和氛围描写。
5. 【绝对禁止】不得添加 forbidden_additions 中列出的任何内容。
6. 覆盖完所有 grounded_facts 后立即停笔，不得为了增加字数而重复或虚构。
7. 可以对原话做轻微整理（去掉口头禅"呢"、"啊"、语气词），但不得改变意思。
8. 不确定的事情必须保留讲述者自己的不确定语气（"好像是"、"我记不清了"）。
"""

_WRITE_USER = """\
请按照以下微纲，写出本章的完整正文。

章节标题：{title}
上一章结尾（承接用）：{prev_ending}

微纲：
{outline_json}

本章可用事件详情（全部覆盖，覆盖完即停）：
{grounded_facts_json}

可用原话细节（allowed_details，感官描写只能从这里取）：
{allowed_details_json}

禁止添加的内容类型：
{forbidden_additions_json}

Story Bible：
{bible_json}

要求：
- 输出纯中文 prose，不加任何 JSON 包装、不加标题、不加"第X章"字样。
- 覆盖完所有事件后立即停笔，字数由内容自然决定，不得为凑字数重复或虚构。
- 结束后在 ===END=== 之后另起两行写出：
  used_fact_ids: evt-0001, evt-0003
  used_detail_ids: dtl-0001, dtl-0005

直接开始正文，不要有任何前言。
"""


def _parse_used_ids(metadata: str, key: str) -> list[str]:
    pattern = rf"^{re.escape(key)}\s*[:：]\s*(.+)$"
    for line in metadata.splitlines():
        match = re.match(pattern, line.strip())
        if not match:
            continue
        return [
            item.strip()
            for item in re.split(r"[,，、\s]+", match.group(1))
            if item.strip()
        ]
    return []


def _split_sentences(body: str) -> list[str]:
    return [
        part.strip()
        for part in re.findall(r"[^。！？!?；;\n]+[。！？!?；;]?", body)
        if part.strip()
    ]


def _chunk_body_for_audit(body: str, max_chars: int = 700) -> list[str]:
    sentences = _split_sentences(body)
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        if current and len(current) + len(sentence) > max_chars:
            chunks.append(current)
            current = sentence
        else:
            current += sentence
    if current:
        chunks.append(current)
    return chunks



def write_chapter(packet: dict, story_bible: dict,
                  prev_ending: str, openrouter_key: str) -> dict:
    from openai import OpenAI
    client = OpenAI(api_key=openrouter_key, base_url="https://openrouter.ai/api/v1")

    grounded_facts = packet.get("grounded_facts", [])

    # Compact bible for prompt
    bible_compact = {
        "name_map": story_bible.get("name_map", []),
        "place_map": story_bible.get("place_map", []),
        "style_profile": story_bible.get("style_profile", {}),
        "prev_chapters": [s["title"] for s in story_bible.get("chapter_synopses", [])],
    }

    # Step 1: Generate micro-outline (groups facts into beats, no word count)
    print(f"  [Write] Generating micro-outline for [{packet['slug']}] ...", flush=True)
    outline_raw = _llm(client, [
        {"role": "system", "content": _OUTLINE_SYS},
        {"role": "user", "content": _OUTLINE_USER.format(
            title=packet["title"],
            theme=packet["theme"],
            opening_note=packet.get("opening_note", ""),
            closing_note=packet.get("closing_note", ""),
            all_facts_json=json.dumps(
                [{"id": f["fact_id"], "claim": f["claim"],
                  "people": f.get("people", []), "places": f.get("places", []),
                  "time": f.get("time", "")}
                 for f in grounded_facts], ensure_ascii=False),
            quotes_json=json.dumps(packet["quote_candidates"], ensure_ascii=False),
            bible_json=json.dumps(bible_compact, ensure_ascii=False),
        )},
    ], max_tokens=2048)
    outline = json.loads(outline_raw)

    # Step 2: Write body — max_tokens estimated from evidence count, no char target
    body_max_tokens = _estimate_max_tokens(grounded_facts)
    print(f"  [Write] Writing body ({len(grounded_facts)} facts, max_tokens={body_max_tokens}) ...", flush=True)
    body_raw = _llm(client, [
        {"role": "system", "content": _WRITE_SYS},
        {"role": "user", "content": _WRITE_USER.format(
            title=packet["title"],
            prev_ending=prev_ending or "（这是第一章，无前文）",
            outline_json=json.dumps(outline, ensure_ascii=False),
            grounded_facts_json=json.dumps(grounded_facts, ensure_ascii=False),
            allowed_details_json=json.dumps(packet.get("allowed_details", []), ensure_ascii=False),
            forbidden_additions_json=json.dumps(packet.get("forbidden_additions", []), ensure_ascii=False),
            bible_json=json.dumps(bible_compact, ensure_ascii=False),
        )},
    ], json_mode=False, max_tokens=body_max_tokens, temperature=0.35)

    # Parse body and source ids from response
    if "===END===" in body_raw:
        parts = body_raw.split("===END===", 1)
        body = parts[0].strip()
        metadata = parts[1].strip()
        used_fact_ids = _parse_used_ids(metadata, "used_fact_ids")
        used_detail_ids = _parse_used_ids(metadata, "used_detail_ids")
    else:
        body = body_raw.strip()
        used_fact_ids = [f.get("fact_id", "") for f in grounded_facts]
        used_detail_ids = []

    print(f"  [Write] Done — {len(body)} chars, {len(used_fact_ids)} fact_ids", flush=True)

    return {
        "slug": packet["slug"],
        "title": packet["title"],
        "body": body,
        "used_fact_ids": used_fact_ids,
        "used_detail_ids": used_detail_ids,
        "actual_chars": len(body),
        "fact_count": len(grounded_facts),
        "micro_outline": outline,
    }


# ── Agent 6: Audit & Repair ────────────────────────────────────────────────────

_AUDIT_SYS = """\
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

_AUDIT_USER = """\
可用事实（source of truth）：
{grounded_facts_json}

可用原话细节：
{allowed_details_json}

正文：
{body}

输出格式：
{{
  "atomic_units": ["我1938年出生在松江", "母亲正怀着我"],
  "claims": [
    {{
      "sentence": "1938年农历二月初一，我出生在松江。",
      "claim": "我1938年农历二月初一出生在松江",
      "status": "supported",
      "support_ids": ["evt-0001"]
    }},
    {{
      "sentence": "那间土房进门就是灶台。",
      "claim": "土房里有灶台",
      "status": "unsupported",
      "support_ids": []
    }}
  ],
  "summary": {{
    "total_claims": 12,
    "supported": 9,
    "unsupported": 2,
    "inferred": 1
  }}
}}
"""

_REPAIR_SYS = """\
你是一位口述史编辑。你的任务是从回忆录正文中删除没有证据支撑的句子。

规则（严格遵守）：
1. 只删除，不添加任何新内容。
2. 不改写保留的句子（保留句字句不变）。
3. 删除后确保上下文连贯（如果删除导致段落断裂，可删除整段，不得用新内容填补）。
4. 输出纯中文正文，不加任何说明。
"""

_REPAIR_USER = """\
原稿：
{body}

需要删除的句子（逐字匹配）：
{unsupported_sentences_json}

请输出删除后的正文：
"""


def audit_chapter(draft: dict, packet: dict, openrouter_key: str) -> dict:
    from openai import OpenAI
    client = OpenAI(api_key=openrouter_key, base_url="https://openrouter.ai/api/v1")

    claims: list[dict] = []
    audit_errors: list[str] = []
    chunks = _chunk_body_for_audit(draft.get("body", ""))
    if not chunks:
        return {
            "verdict": "pass",
            "claims": [],
            "unsupported_sentences": [],
            "unsupported_count": 0,
            "audit_errors": [],
        }

    for chunk in chunks:
        raw = _llm(client, [
            {"role": "system", "content": _AUDIT_SYS},
            {"role": "user", "content": _AUDIT_USER.format(
                grounded_facts_json=json.dumps(packet.get("grounded_facts", []), ensure_ascii=False),
                allowed_details_json=json.dumps(packet.get("allowed_details", []), ensure_ascii=False),
                body=chunk,
            )},
        ], max_tokens=4096)

        try:
            result = json.loads(raw)
        except json.JSONDecodeError as exc:
            audit_errors.append(f"{exc.msg} at char {exc.pos}")
            claims.extend(
                {
                    "sentence": sentence,
                    "claim": sentence,
                    "status": "unsupported",
                    "support_ids": [],
                    "audit_error": "invalid_json",
                }
                for sentence in _split_sentences(chunk)
            )
            continue
        claims.extend(result.get("claims", []))

    unsupported = [claim for claim in claims if claim.get("status") == "unsupported"]
    return {
        "verdict": "pass" if not unsupported else "fail",
        "claims": claims,
        "unsupported_sentences": [
            claim.get("sentence", "") for claim in unsupported if claim.get("sentence")
        ],
        "unsupported_count": len(unsupported),
        "audit_errors": audit_errors,
    }


def repair_chapter(draft: dict, audit_result: dict, openrouter_key: str) -> dict:
    unsupported_sentences = audit_result.get("unsupported_sentences", [])
    if not unsupported_sentences:
        return {**draft, "actual_chars": len(draft.get("body", ""))}

    from openai import OpenAI
    client = OpenAI(api_key=openrouter_key, base_url="https://openrouter.ai/api/v1")

    body = draft.get("body", "")
    repaired = _llm(client, [
        {"role": "system", "content": _REPAIR_SYS},
        {"role": "user", "content": _REPAIR_USER.format(
            body=body,
            unsupported_sentences_json=json.dumps(unsupported_sentences, ensure_ascii=False),
        )},
    ], json_mode=False, max_tokens=max(512, int(len(body) / 1.8) + 200), temperature=0.1).strip()

    if len(repaired) > len(body) or any(sentence in repaired for sentence in unsupported_sentences):
        repaired = body
        for sentence in unsupported_sentences:
            repaired = repaired.replace(sentence, "")
        repaired = re.sub(r"\n{3,}", "\n\n", repaired).strip()

    return {
        **draft,
        "body": repaired,
        "actual_chars": len(repaired),
    }


# ── Agent 7: Polish ───────────────────────────────────────────────────────────

_POLISH_SYS = """\
你是一位口述史文稿润色师。你的任务是把第一人称回忆录从"转写拼接风格"提升为"散文叙述风格"，
同时严格保持零虚构原则。

润色规则（严格遵守）：
1. 【允许】合并短句、调整语序、加过渡词（"那时候"、"后来"、"就这样"）。
2. 【允许】把重复的句子结构变换一下、把流水账式的"然后…然后…"改成更自然的叙述节奏。
3. 【允许】把口语化的表达做轻微书面化（但保留老一辈的语气和词汇特色）。
4. 【绝对禁止】不得添加任何在 grounded_facts 中不存在的事实、细节、场景、对话或感官描写。
5. 【绝对禁止】不得删除任何 grounded_facts 中的信息（只改表达，不丢内容）。
6. 全程第一人称「我」，不得改成第三人称。
7. 输出纯中文正文，不加任何说明或标注。

记住：改变的是节奏和表达方式，不是内容本身。
"""

_POLISH_USER = """\
请润色以下回忆录正文。

章节标题：{title}

原稿：
{body}

本章事实边界（只能包含这些事实，不得添加其他）：
{grounded_facts_json}

直接输出润色后的正文，不加任何前言：
"""


POLISH_MIN_LENGTH_RATIO = 0.8


def _strip_leading_chapter_title(body: str, title: str) -> str:
    lines = body.strip().splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    if lines and lines[0].strip() == title.strip():
        lines.pop(0)
        while lines and not lines[0].strip():
            lines.pop(0)
    return "\n".join(lines).strip()


def _polish_dropped_too_much_content(original: str, candidate: str) -> bool:
    if not original:
        return False
    return len(candidate) < int(len(original) * POLISH_MIN_LENGTH_RATIO)


def polish_chapter(draft: dict, packet: dict, openrouter_key: str) -> dict:
    from openai import OpenAI
    client = OpenAI(api_key=openrouter_key, base_url="https://openrouter.ai/api/v1")

    body = draft.get("body", "")
    grounded_facts = packet.get("grounded_facts", [])

    polish_max_tokens = _estimate_max_tokens(grounded_facts)

    polished = _llm(client, [
        {"role": "system", "content": _POLISH_SYS},
        {"role": "user", "content": _POLISH_USER.format(
            title=draft.get("title", ""),
            body=body,
            grounded_facts_json=json.dumps(
                [{"id": f["fact_id"], "claim": f["claim"]}
                 for f in grounded_facts], ensure_ascii=False),
        )},
    ], json_mode=False, max_tokens=polish_max_tokens, temperature=0.3).strip()

    polished = _strip_leading_chapter_title(polished, draft.get("title", ""))
    if _polish_dropped_too_much_content(body, polished):
        return {
            **draft,
            "actual_chars": len(body),
            "polished": False,
            "polish_rejected_reason": "candidate_dropped_too_much_content",
        }

    return {**draft, "body": polished, "actual_chars": len(polished), "polished": True}


# ── Agent 8: Review & Revise ───────────────────────────────────────────────────

_REVIEW_SYS = """\
你是一位回忆录质检员。你的任务是审校章节草稿，输出结构化质检报告。

注意：事实审计、长度检查和事件覆盖检查已由系统自动完成，你只需审校以下两项：
1. [hard] 第一人称：是否全程第一人称「我」，无第三人称指代讲述者？"她/他"指代母亲、父亲、老师等其他人物时不算问题。
2. [soft] 叙事质量：是否通顺、朴素，是否像回忆录而非摘要？
3. [soft] 过渡：结尾是否为下一章留出了承接？

输出必须是合法 JSON，不加额外说明。
"""

_REVIEW_USER = """\
请审校以下章节正文（正文可能被截断，但质量判断基于所示内容）。

章节标题：{title}

Story Bible：
{bible_json}

前序章节摘要（保持一致性用）：
{prev_synopses}

正文（前5000字）：
{body}

输出格式：
{{
  "issues": [
    {{"type": "pov", "severity": "hard", "detail": "第二段出现了第三人称'她'"}},
    {{"type": "style", "severity": "soft", "detail": "结尾缺少过渡句"}}
  ],
  "rewrite_brief": {{
    "keep": ["第二段关于离家的细节"],
    "fix": ["把第三人称改成第一人称", "把结尾改成有过渡的句子"],
    "do_not_change": ["母亲称谓", "松江地名"]
  }},
  "synopsis_for_bible": "本章讲述讲述者1938年出生于松江，早产，由祖母抚养，亲历日本占领。"
}}
"""

def review_chapter(draft: dict, packet: dict, story_bible: dict,
                   approved: list[dict], openrouter_key: str) -> dict:
    from openai import OpenAI
    client = OpenAI(api_key=openrouter_key, base_url="https://openrouter.ai/api/v1")

    body = draft["body"]
    char_count = len(body)

    # ── LLM qualitative check (first 5000 chars only) ────────────────────────
    bible_compact = {
        "name_map": story_bible.get("name_map", []),
        "place_map": story_bible.get("place_map", []),
        "timeline_anchors": story_bible.get("timeline_anchors", []),
    }
    prev_synopses = [ch.get("synopsis", "") for ch in story_bible.get("chapter_synopses", [])]

    llm_raw = _llm(client, [
        {"role": "system", "content": _REVIEW_SYS},
        {"role": "user", "content": _REVIEW_USER.format(
            title=draft["title"],
            bible_json=json.dumps(bible_compact, ensure_ascii=False),
            prev_synopses=json.dumps(prev_synopses, ensure_ascii=False),
            body=body[:5000] + ("..." if len(body) > 5000 else ""),
        )},
    ], max_tokens=1024)

    llm_result = json.loads(llm_raw)

    all_issues = llm_result.get("issues", [])
    has_hard_fail = any(issue.get("severity") == "hard" for issue in all_issues)

    return {
        "pass": not has_hard_fail,
        "char_count": char_count,
        "issues": all_issues,
        "rewrite_brief": llm_result.get("rewrite_brief", {}),
        "synopsis_for_bible": llm_result.get("synopsis_for_bible", ""),
    }


# ── Orchestrator ───────────────────────────────────────────────────────────────

def generate_narrative_v3(fragments: list[dict], raw_segments: list[dict],
                          openrouter_key: str,
                          checkpoint_path: Path | None = None) -> dict:
    """
    Full narrative pipeline. Saves checkpoint JSON after each major stage.
    checkpoint_path: if provided, saves/resumes intermediate state.
    """

    ckpt: dict = {}
    if checkpoint_path and checkpoint_path.exists():
        ckpt = json.loads(checkpoint_path.read_text())
        print(f"[Narrative] Resuming from checkpoint: {list(ckpt.keys())}", flush=True)

    def save_ckpt():
        if checkpoint_path:
            checkpoint_path.write_text(json.dumps(ckpt, ensure_ascii=False, indent=2))

    if ckpt.get("version") != "v3":
        if ckpt.get("approved_chapters"):
            print("[Checkpoint] Existing approved_chapters are from pre-v3; regenerating chapters.", flush=True)
            ckpt.pop("approved_chapters", None)
            story_bible_ckpt = ckpt.setdefault("story_bible", {})
            story_bible_ckpt["chapter_synopses"] = []
        ckpt["version"] = "v3"
        save_ckpt()

    # ── Stage 1: Canonicalize ─────────────────────────────────────────────────
    if "canon" not in ckpt or "_next_batch" in ckpt.get("canon", {}):
        # Either fresh start or mid-canonicalization resume
        in_progress = ckpt.get("canon", {}) if "_next_batch" in ckpt.get("canon", {}) else None
        if in_progress:
            print(f"\n[Stage 1/6] Resuming canonicalization from batch "
                  f"{in_progress['_next_batch']} ...", flush=True)
        else:
            print("\n[Stage 1/6] Canonicalizing fragments ...", flush=True)
            ckpt["canon"] = {}  # placeholder so save_ckpt persists partials
        result = canonicalize_events(fragments, raw_segments, openrouter_key,
                                     canon_ckpt=ckpt["canon"],
                                     on_batch_save=save_ckpt)
        ckpt["canon"] = result  # overwrite with final (removes _next_batch)
        save_ckpt()
    else:
        missing_grounding = any(
            not event.get("raw_quote")
            for event in ckpt["canon"].get("canonical_events", [])
        )
        if missing_grounding:
            print("[Canon] Adding raw_quote/source_segment_texts to checkpoint events ...", flush=True)
            _attach_event_sources(ckpt["canon"].get("canonical_events", []), fragments, raw_segments)
            save_ckpt()
        print(f"[Stage 1/6] Canon: loaded from checkpoint "
              f"({len(ckpt['canon']['canonical_events'])} events)", flush=True)

    canon = ckpt["canon"]

    # ── Stage 2: Timeline ─────────────────────────────────────────────────────
    if "timeline" not in ckpt:
        print("\n[Stage 2/6] Resolving timeline ...", flush=True)
        ckpt["timeline"] = resolve_timeline(canon, openrouter_key)
        save_ckpt()
    else:
        print("[Timeline] Loaded from checkpoint", flush=True)

    timeline = ckpt["timeline"]
    if any(not event.get("raw_quote") for event in timeline.get("ordered_events", [])):
        print("[Timeline] Adding raw_quote/source_segment_texts to ordered events ...", flush=True)
        _attach_event_sources(timeline.get("ordered_events", []), fragments, raw_segments)
        save_ckpt()

    # ── Stage 3: Plan ─────────────────────────────────────────────────────────
    if "plan" not in ckpt:
        print("\n[Stage 3/6] Planning book ...", flush=True)
        chapter_plan, story_bible = plan_book(timeline, openrouter_key)
        ckpt["plan"] = chapter_plan
        ckpt["story_bible"] = story_bible
        save_ckpt()
    else:
        print(f"[Plan] Loaded from checkpoint ({len(ckpt['plan'])} chapters)", flush=True)

    chapter_plan = ckpt["plan"]
    story_bible = ckpt["story_bible"]
    ordered_events = timeline["ordered_events"]

    # ── Stage 4: Detail Bank ──────────────────────────────────────────────────
    if "detail_bank" not in ckpt:
        print("\n[Stage 4/6] Building detail bank ...", flush=True)
        ckpt["detail_bank"] = build_detail_bank(raw_segments)
        save_ckpt()
        print(f"[DetailBank] {len(ckpt['detail_bank'].get('details', []))} details", flush=True)
    else:
        print(f"[DetailBank] Loaded from checkpoint "
              f"({len(ckpt['detail_bank'].get('details', []))} details)", flush=True)
    detail_bank = ckpt["detail_bank"]

    # ── Stage 5-6: Per-chapter loop ───────────────────────────────────────────
    approved = ckpt.get("approved_chapters", [])
    done_slugs = {ch["slug"] for ch in approved}

    print(f"\n[Stage 5-6/6] Writing {len(chapter_plan)} chapters "
          f"({len(done_slugs)} already done) ...", flush=True)

    for ch_spec in chapter_plan:
        slug = ch_spec["slug"]
        if slug in done_slugs:
            print(f"  [{slug}] Already done, skipping.", flush=True)
            continue

        print(f"\n  ── Chapter: {ch_spec['title']} [{slug}] ──", flush=True)
        packet = build_chapter_packet(ch_spec, story_bible, ordered_events, detail_bank)
        print(f"  [Packet] {len(packet['events'])} events, "
              f"{len(packet['grounded_facts'])} facts, "
              f"{len(packet['allowed_details'])} details", flush=True)

        # Previous chapter ending (last ~150 chars for tone continuity)
        prev_ending = ""
        if approved:
            prev_ending = approved[-1]["body"][-150:]

        # Write
        draft = write_chapter(packet, story_bible, prev_ending, openrouter_key)

        # Audit → repair by deletion only if needed
        print(f"  [Audit] Checking unsupported claims for [{slug}] ...", flush=True)
        audit = audit_chapter(draft, packet, openrouter_key)
        if audit["verdict"] == "fail":
            before_chars = len(draft["body"])
            print(f"  [Audit] FAIL — {audit['unsupported_count']} unsupported, repairing ...", flush=True)
            draft = repair_chapter(draft, audit, openrouter_key)
            print(f"  [Repair] {before_chars} → {len(draft['body'])} chars", flush=True)
            audit = audit_chapter(draft, packet, openrouter_key)
            print(f"  [Audit] After repair: {audit['verdict']} "
                  f"(unsupported={audit['unsupported_count']})", flush=True)
        else:
            print("  [Audit] PASS (unsupported=0)", flush=True)
        draft["audit"] = audit

        # Polish prose (improve flow without adding facts) → re-audit to verify
        print(f"  [Polish] Polishing [{slug}] ...", flush=True)
        before_polish = draft
        draft = polish_chapter(draft, packet, openrouter_key)
        print(f"  [Polish] Done — {len(before_polish['body'])} → {len(draft['body'])} chars", flush=True)

        audit_after_polish = audit_chapter(draft, packet, openrouter_key)
        if audit_after_polish["verdict"] == "fail":
            print(f"  [Polish] Audit FAIL after polish ({audit_after_polish['unsupported_count']} unsupported) "
                  f"— reverting to pre-polish version", flush=True)
            draft = before_polish
        else:
            print("  [Polish] Audit PASS — keeping polished version", flush=True)
            draft["audit"] = audit_after_polish

        # Review style/POV only. No length, coverage, or factual rewrite here.
        print(f"  [Review] Checking [{slug}] ...", flush=True)
        review = review_chapter(draft, packet, story_bible, approved, openrouter_key)
        draft["review"] = review
        if review.get("pass", False):
            print(f"  [Review] PASS ({len(draft['body'])} chars)", flush=True)
        else:
            hard_fails = [i for i in review.get("issues", []) if i.get("severity") == "hard"]
            print(f"  [Review] WARN — {len(hard_fails)} hard style/POV issues", flush=True)

        # Commit chapter + update story bible
        synopsis = review.get("synopsis_for_bible", "")
        story_bible["chapter_synopses"].append({
            "slug": slug,
            "title": ch_spec["title"],
            "synopsis": synopsis,
        })
        approved.append(draft)
        ckpt["approved_chapters"] = approved
        ckpt["story_bible"] = story_bible
        save_ckpt()
        print(f"  [{slug}] Committed — {len(draft['body'])} chars", flush=True)

    return {
        "version": "v3",
        "detail_bank_size": len(detail_bank.get("details", [])),
        "chapters": [
            {
                "slug": ch["slug"],
                "title": ch["title"],
                "body": ch["body"],
                "used_fact_ids": ch.get("used_fact_ids", []),
                "used_detail_ids": ch.get("used_detail_ids", []),
                "fragment_ids": ch.get("used_fact_ids", []),
                "actual_chars": ch.get("actual_chars", len(ch.get("body", ""))),
                "fact_count": ch.get("fact_count"),
                "audit": ch.get("audit", {}),
            }
            for ch in approved
        ]
    }


def generate_narrative_v2(fragments: list[dict], raw_segments: list[dict],
                          openrouter_key: str,
                          checkpoint_path: Path | None = None) -> dict:
    return generate_narrative_v3(
        fragments,
        raw_segments,
        openrouter_key,
        checkpoint_path=checkpoint_path,
    )


# ── CLI entry point ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="长卷 Narrative Agent v3")
    parser.add_argument("pipeline_json", type=Path,
                        help="path to pipeline.json (output of batch_ingest.py)")
    parser.add_argument("--out", type=Path, default=None,
                        help="output path (default: overwrite pipeline_json narrative field)")
    parser.add_argument("--ckpt", type=Path, default=None,
                        help="checkpoint path for resuming (default: <pipeline_json>.narr_ckpt.json)")
    args = parser.parse_args()

    openrouter_key = load_openrouter_key()

    data = json.loads(args.pipeline_json.read_text())
    fragments = data.get("claims", data.get("fragments", []))
    segments = data.get("segments", [])

    print(f"Loaded: {len(fragments)} fragments, {len(segments)} segments", flush=True)

    ckpt_path = args.ckpt or args.pipeline_json.with_suffix(".narr_ckpt.json")
    narrative = generate_narrative_v3(fragments, segments, openrouter_key,
                                      checkpoint_path=ckpt_path)

    out_path = args.out or args.pipeline_json
    data["narrative"] = narrative
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"\n[Done] Narrative written → {out_path}")
    print(f"\n{'=' * 60}")
    print("NARRATIVE PREVIEW")
    print("=" * 60)
    for ch in narrative.get("chapters", []):
        print(f"\n## {ch['title']} [{ch['slug']}] — {len(ch['body'])} 字")
        print(ch["body"][:400])
        if len(ch["body"]) > 400:
            print("  ...")


if __name__ == "__main__":
    main()
