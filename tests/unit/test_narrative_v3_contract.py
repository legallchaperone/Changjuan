from __future__ import annotations

import json
import sys
import types
from pathlib import Path

from scripts import narrative_agent as narrative


def _install_fake_openai(monkeypatch) -> None:
    fake_openai = types.SimpleNamespace(OpenAI=lambda **_kwargs: object())
    monkeypatch.setitem(sys.modules, "openai", fake_openai)


def test_canonicalize_events_attaches_raw_quote_and_source_segments(monkeypatch) -> None:
    _install_fake_openai(monkeypatch)

    def fake_llm(_client, _messages, **_kwargs) -> str:
        return json.dumps(
            {
                "canonical_events": [
                    {
                        "event_id": "evt-local",
                        "summary_1p": "我1938年出生，母亲正怀着我。",
                        "supporting_fragment_ids": ["frag-1", "frag-2"],
                        "quote_candidates": [],
                        "importance": 0.95,
                    }
                ],
                "name_normalizations": [],
                "place_normalizations": [],
                "conflicts": [],
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(narrative, "_llm", fake_llm)
    fragments = [
        {
            "id": "frag-1",
            "fragment_text": "我是1938年农历二月初一生的",
            "source_segment_ids": ["seg-1"],
        },
        {
            "id": "frag-2",
            "fragment_text": "那时候日本人来了，我妈妈正好怀着我",
            "source_segment_ids": ["seg-2"],
        },
    ]
    raw_segments = [
        {"id": "seg-1", "speaker": "storyteller", "text": "我是1938年农历二月初一生的"},
        {"id": "seg-2", "speaker": "storyteller", "text": "那时候日本人来了，我妈妈正好怀着我"},
    ]

    result = narrative.canonicalize_events(
        fragments,
        raw_segments,
        "openrouter-key",
        batch_size=10,
    )

    event = result["canonical_events"][0]
    assert event["raw_quote"] == "我是1938年农历二月初一生的 那时候日本人来了，我妈妈正好怀着我"
    assert event["source_segment_texts"] == [
        "我是1938年农历二月初一生的",
        "那时候日本人来了，我妈妈正好怀着我",
    ]


def test_build_detail_bank_extracts_traceable_storyteller_details() -> None:
    raw_segments = [
        {
            "id": "seg-1",
            "speaker": "storyteller",
            "text": "脸上抹得漆黑漆黑的，把土都抹在脸上到处逃",
        },
        {
            "id": "seg-2",
            "speaker": "storyteller",
            "text": "我就太记不清了，好像是已经考上中学了",
        },
        {"id": "seg-3", "speaker": "interviewer", "text": "后来呢？"},
    ]

    detail_bank = narrative.build_detail_bank(raw_segments)

    assert [detail["text"] for detail in detail_bank["details"]] == [
        "脸上抹得漆黑漆黑的，把土都抹在脸上到处逃",
        "我就太记不清了，好像是已经考上中学了",
    ]
    assert detail_bank["details"][0]["type"] == "verbatim_quote"
    assert detail_bank["details"][1]["type"] == "uncertainty"
    source_texts = {segment["text"] for segment in raw_segments}
    assert all(detail["text"] in source_texts for detail in detail_bank["details"])


def test_build_chapter_packet_is_grounded_and_does_not_emit_length_targets() -> None:
    chapter_spec = {
        "slug": "childhood",
        "title": "童年",
        "theme": "战乱中的童年",
        "must_cover_event_ids": ["evt-0001"],
        "suggested_event_ids": ["evt-0002"],
        "target_chars": 9000,
    }
    ordered_events = [
        {
            "event_id": "evt-0001",
            "summary_1p": "我出生在松江。",
            "raw_quote": "我是1938年农历二月初一生的",
            "source_segment_texts": ["我是1938年农历二月初一生的"],
            "people": ["母亲"],
            "places": ["松江"],
            "life_stage": "童年",
            "time_span": {"start": "1938"},
            "importance": 0.95,
            "quote_candidates": [],
        },
        {
            "event_id": "evt-0002",
            "summary_1p": "我躲避战乱。",
            "raw_quote": "脸上抹得漆黑漆黑的，把土都抹在脸上到处逃",
            "source_segment_texts": ["脸上抹得漆黑漆黑的，把土都抹在脸上到处逃"],
            "people": ["母亲"],
            "places": ["松江"],
            "life_stage": "童年",
            "importance": 0.7,
            "quote_candidates": [],
        },
    ]
    detail_bank = {
        "details": [
            {
                "detail_id": "dtl-0001",
                "type": "verbatim_quote",
                "text": "脸上抹得漆黑漆黑的，把土都抹在脸上到处逃",
                "source_segment_id": "seg-2",
                "topics": ["童年", "母亲", "战乱"],
            },
            {
                "detail_id": "dtl-0002",
                "type": "voice_marker",
                "text": "把我高兴得不得了",
                "source_segment_id": "seg-9",
                "topics": ["工作"],
            },
        ]
    }

    packet = narrative.build_chapter_packet(chapter_spec, {}, ordered_events, detail_bank)

    for removed_key in ("target_chars", "min_chars", "max_chars", "evidence_score"):
        assert removed_key not in packet
    assert packet["grounded_facts"] == [
        {
            "fact_id": "evt-0001",
            "claim": "我出生在松江。",
            "raw_quote": "我是1938年农历二月初一生的",
            "people": ["母亲"],
            "places": ["松江"],
            "time": "1938",
        },
        {
            "fact_id": "evt-0002",
            "claim": "我躲避战乱。",
            "raw_quote": "脸上抹得漆黑漆黑的，把土都抹在脸上到处逃",
            "people": ["母亲"],
            "places": ["松江"],
            "time": "",
        },
    ]
    assert [detail["detail_id"] for detail in packet["allowed_details"]] == ["dtl-0001"]
    assert any("室内陈设" in item for item in packet["forbidden_additions"])


def test_writer_uses_grounded_ids_and_does_not_expand_short_evidence(monkeypatch) -> None:
    _install_fake_openai(monkeypatch)
    calls: list[list[dict]] = []

    def fake_llm(_client, messages, **kwargs) -> str:
        calls.append(messages)
        if kwargs.get("json_mode", True):
            return json.dumps(
                {
                    "beats": [
                        {
                            "beat_id": 1,
                            "description": "出生记忆",
                            "event_ids": ["evt-0001"],
                            "suggested_quotes": [],
                        }
                    ],
                },
                ensure_ascii=False,
            )
        return "我是1938年农历二月初一生的。\n===END===\nused_fact_ids: evt-0001\nused_detail_ids: dtl-0001"

    monkeypatch.setattr(narrative, "_llm", fake_llm)
    packet = {
        "slug": "childhood",
        "title": "童年",
        "theme": "出生",
        "must_cover_event_ids": ["evt-0001"],
        "events": [],
        "quote_candidates": [],
        "grounded_facts": [
            {
                "fact_id": "evt-0001",
                "claim": "我1938年农历二月初一出生",
                "raw_quote": "我是1938年农历二月初一生的",
            }
        ],
        "allowed_details": [
            {"detail_id": "dtl-0001", "text": "我是1938年农历二月初一生的"}
        ],
        "forbidden_additions": ["未在 grounded_facts 中出现的天气、季节描述"],
    }

    draft = narrative.write_chapter(packet, {}, "", "openrouter-key")

    assert len(calls) == 2
    assert draft["used_fact_ids"] == ["evt-0001"]
    assert draft["used_detail_ids"] == ["dtl-0001"]
    assert "event_ids" not in draft
    assert "insufficient_evidence" not in draft
    for removed_key in ("target_chars", "min_chars", "max_chars"):
        assert removed_key not in draft


def test_audit_and_repair_surface_unsupported_sentences(monkeypatch) -> None:
    _install_fake_openai(monkeypatch)
    responses = iter(
        [
            json.dumps(
                {
                    "atomic_units": ["我1938年出生"],
                    "claims": [
                        {
                            "sentence": "1938年，我出生了。",
                            "claim": "我1938年出生",
                            "status": "supported",
                            "support_ids": ["evt-0001"],
                        },
                        {
                            "sentence": "那间土房进门就是灶台。",
                            "claim": "土房里有灶台",
                            "status": "unsupported",
                            "support_ids": [],
                        },
                    ],
                    "summary": {"total_claims": 2, "supported": 1, "unsupported": 1},
                },
                ensure_ascii=False,
            ),
            "1938年，我出生了。",
        ]
    )
    monkeypatch.setattr(narrative, "_llm", lambda *_args, **_kwargs: next(responses))
    draft = {
        "slug": "childhood",
        "title": "童年",
        "body": "1938年，我出生了。那间土房进门就是灶台。",
    }
    packet = {
        "grounded_facts": [
            {"fact_id": "evt-0001", "claim": "我1938年出生", "raw_quote": "我是1938年生的"}
        ],
        "allowed_details": [],
    }

    audit = narrative.audit_chapter(draft, packet, "openrouter-key")
    repaired = narrative.repair_chapter(draft, audit, "openrouter-key")

    assert audit["verdict"] == "fail"
    assert audit["unsupported_count"] == 1
    assert audit["unsupported_sentences"] == ["那间土房进门就是灶台。"]
    assert len(repaired["body"]) <= len(draft["body"])
    assert "灶台" not in repaired["body"]


def test_audit_invalid_json_fails_closed_without_crashing(monkeypatch) -> None:
    _install_fake_openai(monkeypatch)
    monkeypatch.setattr(narrative, "_llm", lambda *_args, **_kwargs: '{"claims": [')

    audit = narrative.audit_chapter(
        {"body": "我是1938年出生的。那时候日本人来了。"},
        {"grounded_facts": [], "allowed_details": []},
        "openrouter-key",
    )

    assert audit["verdict"] == "fail"
    assert audit["unsupported_sentences"] == ["我是1938年出生的。", "那时候日本人来了。"]
    assert audit["audit_errors"]


def test_polish_strips_leading_chapter_title(monkeypatch) -> None:
    _install_fake_openai(monkeypatch)
    monkeypatch.setattr(
        narrative,
        "_llm",
        lambda *_args, **_kwargs: "童年\n\n我是1938年农历二月初一生的。",
    )

    draft = {"slug": "childhood", "title": "童年", "body": "我是1938年农历二月初一生的。"}
    packet = {
        "grounded_facts": [
            {"fact_id": "evt-0001", "claim": "我1938年出生", "raw_quote": "我是1938年生的"}
        ],
    }

    polished = narrative.polish_chapter(draft, packet, "openrouter-key")

    assert polished["body"] == "我是1938年农历二月初一生的。"
    assert polished["polished"] is True


def test_polish_reverts_when_candidate_drops_too_much_content(monkeypatch) -> None:
    _install_fake_openai(monkeypatch)
    monkeypatch.setattr(narrative, "_llm", lambda *_args, **_kwargs: "我出生了。")

    original = "我出生了。" * 40
    draft = {"slug": "childhood", "title": "童年", "body": original}
    packet = {
        "grounded_facts": [
            {"fact_id": "evt-0001", "claim": "我1938年出生", "raw_quote": "我是1938年生的"}
        ],
    }

    polished = narrative.polish_chapter(draft, packet, "openrouter-key")

    assert polished["body"] == original
    assert polished["polished"] is False
    assert polished["polish_rejected_reason"] == "candidate_dropped_too_much_content"


def test_writer_does_not_apply_hard_character_truncation(monkeypatch) -> None:
    _install_fake_openai(monkeypatch)
    calls = 0

    def fake_llm(_client, _messages, **kwargs) -> str:
        nonlocal calls
        calls += 1
        if kwargs.get("json_mode", True):
            return json.dumps(
                {
                    "beats": [
                        {
                            "beat_id": 1,
                            "description": "出生记忆",
                            "event_ids": ["evt-0001"],
                            "suggested_quotes": [],
                        }
                    ],
                },
                ensure_ascii=False,
            )
        return f"{'我出生了。' * 200}\n===END===\nused_fact_ids: evt-0001\nused_detail_ids:"

    monkeypatch.setattr(narrative, "_llm", fake_llm)
    draft = narrative.write_chapter(
        {
                "slug": "childhood",
                "title": "童年",
                "theme": "出生",
                "must_cover_event_ids": ["evt-0001"],
            "events": [],
            "quote_candidates": [],
            "grounded_facts": [{"fact_id": "evt-0001", "claim": "我出生", "raw_quote": "我出生了"}],
            "allowed_details": [],
            "forbidden_additions": [],
        },
        {},
        "",
        "openrouter-key",
    )

    assert calls == 2
    assert len(draft["body"]) == len("我出生了。" * 200)


def test_review_no_longer_rejects_length_or_coverage(monkeypatch) -> None:
    _install_fake_openai(monkeypatch)
    monkeypatch.setattr(
        narrative,
        "_llm",
        lambda *_args, **_kwargs: json.dumps(
            {
                "issues": [],
                "rewrite_brief": {},
                "synopsis_for_bible": "本章讲出生。",
            },
            ensure_ascii=False,
        ),
    )

    review = narrative.review_chapter(
        {"slug": "childhood", "title": "童年", "body": "我出生了。", "used_fact_ids": []},
        {"target_chars": 1500, "must_cover_event_ids": ["evt-0001"]},
        {},
        [],
        "openrouter-key",
    )

    assert review["pass"] is True
    assert all(issue["type"] not in {"length", "coverage"} for issue in review["issues"])


def test_prompts_and_batch_entrypoint_use_v3_grounding_contract() -> None:
    assert "4000" not in narrative._PLAN_SYS
    assert "6000" not in narrative._PLAN_SYS
    assert "10000" not in narrative._PLAN_SYS
    assert "每个叙事拍点至少包含一个具体场景" not in narrative._WRITE_SYS
    assert "真实性优先于文学性" in narrative._WRITE_SYS
    assert "grounded_facts" in narrative._WRITE_USER
    assert "allowed_details" in narrative._WRITE_USER
    assert hasattr(narrative, "generate_narrative_v3")
    source = Path("scripts/narrative_agent.py").read_text()
    assert "_REWRITE_SYS" not in source
    assert "def rewrite_chapter" not in source
    assert "目标字数" not in source

    batch_ingest_source = Path("scripts/batch_ingest.py").read_text()
    assert "generate_narrative_v3" in batch_ingest_source


def test_v3_orchestrator_migrates_old_checkpoint_and_enriches_timeline(
    tmp_path: Path,
    monkeypatch,
) -> None:
    ckpt_path = tmp_path / "story.narr_ckpt.json"
    ckpt_path.write_text(
        json.dumps(
            {
                "canon": {
                    "canonical_events": [
                        {
                            "event_id": "evt-0001",
                            "summary_1p": "我1938年出生。",
                            "supporting_fragment_ids": ["frag-1"],
                            "importance": 0.95,
                        }
                    ]
                },
                "timeline": {
                    "ordered_events": [
                        {
                            "event_id": "evt-0001",
                            "summary_1p": "我1938年出生。",
                            "supporting_fragment_ids": ["frag-1"],
                            "life_stage": "童年",
                            "importance": 0.95,
                        }
                    ],
                    "life_stages": [],
                    "uncertain_edges": [],
                },
                "plan": [
                    {
                        "slug": "childhood",
                        "title": "童年",
                        "must_cover_event_ids": ["evt-0001"],
                        "suggested_event_ids": [],
                    }
                ],
                "story_bible": {"chapter_synopses": [{"slug": "old", "title": "旧章"}]},
                "approved_chapters": [{"slug": "childhood", "title": "旧童年", "body": "旧正文"}],
            },
            ensure_ascii=False,
        )
    )
    fragments = [
        {
            "id": "frag-1",
            "fragment_text": "我是1938年农历二月初一生的",
            "source_segment_ids": ["seg-1"],
        }
    ]
    raw_segments = [
        {
            "id": "seg-1",
            "speaker": "storyteller",
            "text": "我是1938年农历二月初一生的，那时候我记得很清楚",
        }
    ]

    def fake_write(packet, _story_bible, _prev_ending, _openrouter_key):
        assert packet["grounded_facts"][0]["raw_quote"] == "我是1938年农历二月初一生的"
        return {
            "slug": packet["slug"],
            "title": packet["title"],
            "body": "我是1938年农历二月初一生的。",
            "used_fact_ids": ["evt-0001"],
            "used_detail_ids": [],
            "actual_chars": 16,
            "fact_count": len(packet["grounded_facts"]),
        }

    monkeypatch.setattr(narrative, "write_chapter", fake_write)
    monkeypatch.setattr(
        narrative,
        "polish_chapter",
        lambda draft, *_args, **_kwargs: {**draft, "polished": True},
    )
    monkeypatch.setattr(
        narrative,
        "audit_chapter",
        lambda *_args, **_kwargs: {"verdict": "pass", "unsupported_count": 0, "claims": []},
    )
    monkeypatch.setattr(
        narrative,
        "review_chapter",
        lambda *_args, **_kwargs: {
            "pass": True,
            "issues": [],
            "synopsis_for_bible": "本章讲出生。",
        },
    )

    result = narrative.generate_narrative_v3(
        fragments,
        raw_segments,
        "openrouter-key",
        checkpoint_path=ckpt_path,
    )

    saved = json.loads(ckpt_path.read_text())
    assert result["version"] == "v3"
    assert result["chapters"][0]["body"] == "我是1938年农历二月初一生的。"
    assert saved["version"] == "v3"
    assert saved["approved_chapters"][0]["body"] == "我是1938年农历二月初一生的。"
    assert saved["story_bible"]["chapter_synopses"] == [
        {"slug": "childhood", "title": "童年", "synopsis": "本章讲出生。"}
    ]
