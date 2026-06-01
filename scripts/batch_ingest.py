"""
Batch ingest: local audio file → ASR (Groq Whisper) → extraction (LLM) → narrative (LLM)

Usage:
    python -m scripts.batch_ingest <audio_file> [--out output.json] [--skip-asr transcript.json]

API keys are read from the project root `api_key` file:
  line 1: OpenRouter key
  line 2: DashScope key (legacy, unused)
  line 3: Groq key
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).parent.parent
KEYS_FILE = ROOT / "api_key"


def load_keys() -> tuple[str, str, str]:
    lines = KEYS_FILE.read_text().strip().splitlines()
    openrouter = lines[0].strip()
    dashscope = lines[1].strip() if len(lines) > 1 else ""
    groq = ""
    for line in lines:
        line = line.strip()
        if line.startswith("gsk_"):
            groq = line
            break
    return openrouter, dashscope, groq


# ── ASR ───────────────────────────────────────────────────────────────────────

GROQ_MAX_BYTES = 24 * 1024 * 1024  # 24 MB safety margin under Groq's 25 MB limit


def _split_audio(audio_path: Path) -> list[Path]:
    """Split audio into <24 MB chunks using ffmpeg. Returns list of chunk paths."""
    import subprocess
    size = audio_path.stat().st_size
    if size <= GROQ_MAX_BYTES:
        return [audio_path]

    # Estimate duration then split into equal parts
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)],
        capture_output=True, text=True, check=True,
    )
    duration = float(probe.stdout.strip())
    n_parts = int(size / GROQ_MAX_BYTES) + 1
    chunk_dur = duration / n_parts

    chunks = []
    for i in range(n_parts):
        chunk_path = audio_path.with_suffix(f".chunk{i}.mp3")
        subprocess.run([
            "ffmpeg", "-y", "-i", str(audio_path),
            "-ss", str(i * chunk_dur),
            "-t", str(chunk_dur),
            "-ac", "1",        # mono
            "-ar", "16000",    # 16kHz — sufficient for speech
            "-b:a", "64k",
            str(chunk_path),
        ], check=True, capture_output=True)
        chunks.append(chunk_path)
        print(f"[ASR] Chunk {i+1}/{n_parts}: {chunk_path.name} ({chunk_path.stat().st_size/1e6:.1f} MB)", flush=True)
    return chunks


def transcribe(audio_path: Path, groq_key: str) -> list[dict]:
    from groq import Groq

    client = Groq(api_key=groq_key)
    print(f"[ASR] Groq Whisper large-v3: {audio_path.name} ({audio_path.stat().st_size/1e6:.1f} MB)", flush=True)

    chunks = _split_audio(audio_path)
    segments: list[dict] = []
    time_offset_ms = 0

    for chunk_path in chunks:
        print(f"[ASR] Transcribing {chunk_path.name} ...", flush=True)
        with open(chunk_path, "rb") as f:
            result = client.audio.transcriptions.create(
                model="whisper-large-v3",
                file=f,
                language="zh",
                response_format="verbose_json",
                timestamp_granularities=["segment"],
            )

        for seg in result.segments:
            if isinstance(seg, dict):
                text, start, end, nsp = seg.get("text",""), seg.get("start",0), seg.get("end",0), seg.get("no_speech_prob",0.0)
            else:
                text, start, end, nsp = seg.text, seg.start, seg.end, seg.no_speech_prob
            segments.append({
                "id": str(uuid.uuid4()),
                "speaker": "storyteller",
                "text": text.strip(),
                "start_ms": int(start * 1000) + time_offset_ms,
                "end_ms": int(end * 1000) + time_offset_ms,
                "confidence": round(1.0 - min(abs(nsp), 0.99), 2),
            })

        # Advance offset by chunk duration
        if chunk_path != audio_path:
            time_offset_ms = segments[-1]["end_ms"] if segments else time_offset_ms
            chunk_path.unlink()  # clean up temp chunk

    print(f"[ASR] Done — {len(segments)} segments", flush=True)
    return segments


# ── Diarization (LLM) ─────────────────────────────────────────────────────────

def _load_hf_token() -> str:
    for line in KEYS_FILE.read_text().strip().splitlines():
        line = line.strip()
        if line.startswith("hf_"):
            return line
    raise RuntimeError("HuggingFace token not found in api_key file. Add a line starting with 'hf_'.")


def diarize_segments(segments: list[dict], audio_path: Path) -> list[dict]:
    """Use pyannote.audio speaker-diarization-3.1 to label each segment as storyteller or interviewer."""
    import subprocess
    import tempfile

    import torch
    from pyannote.audio import Pipeline

    hf_token = _load_hf_token()
    print("[Diarize] Loading pyannote speaker-diarization-3.1 ...", flush=True)

    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
        token=hf_token,
    )
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    pipeline.to(torch.device(device))

    # Convert to WAV first — pyannote has sample-count issues with MP3 frame boundaries
    wav_path = Path(tempfile.mktemp(suffix=".wav"))
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(audio_path), "-ac", "1", "-ar", "16000", str(wav_path)],
        check=True, capture_output=True,
    )
    print(f"[Diarize] Running diarization on {audio_path.name} (device={device}) ...", flush=True)
    try:
        diarization = pipeline(str(wav_path))
    finally:
        wav_path.unlink(missing_ok=True)

    # Build a list of (start_ms, end_ms, speaker_label) from pyannote output
    dia_spans: list[tuple[int, int, str]] = []
    # pyannote 4.x returns DiarizeOutput; the annotation is in .speaker_diarization
    annotation = getattr(diarization, "speaker_diarization", diarization)
    for turn, _, speaker in annotation.itertracks(yield_label=True):
        dia_spans.append((int(turn.start * 1000), int(turn.end * 1000), speaker))

    # Identify which pyannote speaker label corresponds to storyteller (longest total speaking time)
    speaker_time: dict[str, int] = {}
    for start, end, spk in dia_spans:
        speaker_time[spk] = speaker_time.get(spk, 0) + (end - start)
    storyteller_label = max(speaker_time, key=speaker_time.__getitem__)
    print(f"[Diarize] Speakers: {speaker_time}  → storyteller={storyteller_label}", flush=True)

    def _get_speaker(start_ms: int, end_ms: int) -> str:
        """Return the dominant speaker for a segment by overlap with diarization spans."""
        mid = (start_ms + end_ms) / 2
        overlaps: dict[str, int] = {}
        for d_start, d_end, spk in dia_spans:
            overlap = max(0, min(end_ms, d_end) - max(start_ms, d_start))
            if overlap > 0:
                overlaps[spk] = overlaps.get(spk, 0) + overlap
        if not overlaps:
            # fallback: find nearest span by midpoint
            nearest = min(dia_spans, key=lambda s: abs((s[0]+s[1])/2 - mid))
            return "storyteller" if nearest[2] == storyteller_label else "interviewer"
        dominant = max(overlaps, key=overlaps.__getitem__)
        return "storyteller" if dominant == storyteller_label else "interviewer"

    interviewer_count = 0
    for seg in segments:
        speaker = _get_speaker(seg["start_ms"], seg["end_ms"])
        seg["speaker"] = speaker
        if speaker == "interviewer":
            interviewer_count += 1

    print(f"[Diarize] Done — storyteller: {len(segments)-interviewer_count}  interviewer: {interviewer_count}", flush=True)
    return segments


# ── Extraction (LLM) ──────────────────────────────────────────────────────────

EXTRACTION_SYSTEM = (ROOT / "packages/prompts/extraction_agent_v1.md").read_text()

EXTRACTION_USER_TMPL = """以下是采访转写片段（JSON 数组），每条有 id、speaker、text 字段。
请按 system prompt 的规则提取记忆片段（memory fragments），返回纯 JSON，格式如下：

{{
  "fragments": [
    {{
      "fragment_text": "（第一人称"我"）...",
      "fragment_type": "family|work|migration|education|life_event",
      "fragment_priority": "P0|P1|P2",
      "source_segment_ids": ["<segment id>", ...],
      "confidence": 0.0-1.0,
      "support_status": "supported|needs_review|unsupported",
      "sensitivity": "normal|sensitive"
    }}
  ]
}}

只输出 JSON，不要加任何解释文字。片段太乱无法理解的直接跳过，不要强行提取。

转写片段：
{segments_json}
"""


def extract_claims(segments: list[dict], openrouter_key: str,
                   checkpoint_path: Path | None = None) -> list[dict]:
    from openai import OpenAI

    client = OpenAI(
        api_key=openrouter_key,
        base_url="https://openrouter.ai/api/v1",
    )

    batch_size = 15
    batches = [segments[i:i+batch_size] for i in range(0, len(segments), batch_size)]

    # Load partial progress from checkpoint if available
    start_batch = 0
    all_fragments: list[dict] = []
    if checkpoint_path and checkpoint_path.exists():
        ckpt = json.loads(checkpoint_path.read_text())
        all_fragments = ckpt.get("fragments", [])
        start_batch = ckpt.get("next_batch", 0)
        if start_batch > 0:
            print(f"[Extraction] Resuming from batch {start_batch+1}/{len(batches)} ({len(all_fragments)} fragments so far)", flush=True)

    print(f"[Extraction] {len(segments)} segments → {len(batches)} batches (size {batch_size})", flush=True)

    for i, batch in enumerate(batches):
        if i < start_batch:
            continue
        print(f"[Extraction] Batch {i+1}/{len(batches)} ...", flush=True)
        segments_json = json.dumps(
            [{"id": s["id"], "speaker": s["speaker"], "text": s["text"]} for s in batch],
            ensure_ascii=False, indent=2
        )

        # Retry on rate limit or transient connection errors with exponential backoff
        for attempt in range(5):
            try:
                response = client.chat.completions.create(
                    model="deepseek/deepseek-chat",
                    messages=[
                        {"role": "system", "content": EXTRACTION_SYSTEM},
                        {"role": "user", "content": EXTRACTION_USER_TMPL.format(segments_json=segments_json)},
                    ],
                    temperature=0.1,
                    max_tokens=4096,
                    response_format={"type": "json_object"},
                )
                break
            except Exception as e:
                is_rate_limit = "429" in str(e)
                is_connection = any(k in str(type(e)) for k in ("ConnectError", "ConnectionError", "APIConnectionError")) or "EOF" in str(e) or "Connection error" in str(e)
                if (is_rate_limit or is_connection) and attempt < 4:
                    wait = 30 * (2 ** attempt) if is_rate_limit else 15 * (attempt + 1)
                    label = "Rate limited" if is_rate_limit else "Connection error"
                    print(f"[Extraction] {label}, waiting {wait}s (attempt {attempt+1}/5) ...", flush=True)
                    time.sleep(wait)
                else:
                    raise

        raw = response.choices[0].message.content
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            print(f"[Extraction] Batch {i+1} — JSON truncated, skipping", flush=True)
            parsed = {}

        batch_fragments = parsed.get("fragments", parsed.get("claims", []))
        for f in batch_fragments:
            f.setdefault("id", str(uuid.uuid4()))
            if "claim_text" in f and "fragment_text" not in f:
                f["fragment_text"] = f.pop("claim_text")
            if "claim_type" in f and "fragment_type" not in f:
                f["fragment_type"] = f.pop("claim_type")
            if "claim_priority" in f and "fragment_priority" not in f:
                f["fragment_priority"] = f.pop("claim_priority")
        all_fragments.extend(batch_fragments)
        print(f"[Extraction] Batch {i+1} → {len(batch_fragments)} fragments", flush=True)

        # Save checkpoint every 20 batches
        if checkpoint_path and (i + 1) % 20 == 0:
            checkpoint_path.write_text(json.dumps(
                {"fragments": all_fragments, "next_batch": i + 1},
                ensure_ascii=False
            ))
            print(f"[Extraction] Checkpoint saved at batch {i+1}", flush=True)

    # Clear checkpoint on completion
    if checkpoint_path and checkpoint_path.exists():
        checkpoint_path.unlink()

    print(f"[Extraction] Total: {len(all_fragments)} fragments", flush=True)
    p0 = [f for f in all_fragments if f.get("fragment_priority") == "P0"]
    print(f"  P0: {len(p0)}  P1+P2: {len(all_fragments)-len(p0)}", flush=True)
    return all_fragments


# ── Narrative (LLM) ───────────────────────────────────────────────────────────

NARRATIVE_SYSTEM = (ROOT / "packages/prompts/narrative_agent_v1.md").read_text()

NARRATIVE_USER_TMPL = """请根据以下两部分内容生成家庭故事草稿，返回纯 JSON：

{{
  "chapters": [
    {{
      "slug": "opening|childhood-family|education|work-migration|family|remembered-events|message-to-descendants",
      "title": "章节标题",
      "body": "章节正文（第一人称"我"，叙述性文字，不是列表）",
      "fragment_ids": ["<fragment id>", ...]
    }}
  ]
}}

只输出 JSON，不要加任何解释文字。

---

## Part 1 — 记忆片段（结构骨架，确定章节主题和关键事实）

{claims_json}

---

## Part 2 — 原始转写片段（讲述者原话，取细节、语气、具体表达）

{segments_json}
"""


def generate_narrative(claims: list[dict], segments: list[dict], openrouter_key: str) -> dict:
    from openai import OpenAI

    client = OpenAI(
        api_key=openrouter_key,
        base_url="https://openrouter.ai/api/v1",
    )

    # Build fragment list: all P0 + up to 100 P1 (tested limit before silent context overflow)
    # Chinese tokenizes at ~2 chars/token; P0+100P1 ≈ 29k tokens which reliably succeeds
    p0 = [f for f in claims if f.get("fragment_priority") == "P0"]
    p1 = [f for f in claims if f.get("fragment_priority") == "P1"]
    selected = p0 + p1[:100]
    minimal_claims = [
        {"id": f["id"], "fragment_text": f["fragment_text"],
         "fragment_type": f.get("fragment_type", ""), "fragment_priority": f.get("fragment_priority", "")}
        for f in selected
    ]
    claims_json = json.dumps(minimal_claims, ensure_ascii=False)

    # Sample up to 100 evenly-spaced segments as texture
    step = max(1, len(segments) // 100)
    sample_segs = [{"id": s["id"], "text": s["text"]} for s in segments[::step]][:100]
    segments_json = json.dumps(sample_segs, ensure_ascii=False)

    print(f"[Narrative] {len(selected)} fragments (P0={len(p0)}, P1_sample={min(300,len(p1))}) + {len(sample_segs)} sampled segments ...", flush=True)

    for attempt in range(3):
        response = client.chat.completions.create(
            model="deepseek/deepseek-chat",
            messages=[
                {"role": "system", "content": NARRATIVE_SYSTEM},
                {"role": "user", "content": NARRATIVE_USER_TMPL.format(
                    claims_json=claims_json,
                    segments_json=segments_json,
                )},
            ],
            temperature=0.3,
            max_tokens=16384,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content if response.choices else None
        if content:
            break
        finish = response.choices[0].finish_reason if response.choices else "no choices"
        print(f"[Narrative] Empty response (attempt {attempt+1}/3), finish_reason={finish}, retrying ...", flush=True)
        time.sleep(15)
    if not content:
        finish = response.choices[0].finish_reason if response.choices else "no choices"
        raise RuntimeError(f"Narrative LLM returned empty response after 3 attempts. finish_reason={finish}")
    narrative = json.loads(content)
    for ch in narrative.get("chapters", []):
        fids = ch.get("fragment_ids", ch.get("claim_ids", []))
        print(f"  [{ch['slug']}] {ch['title']} — {len(fids)} fragments", flush=True)
    return narrative


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("audio", type=Path, help="path to audio file")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--skip-asr", type=Path, default=None,
                        help="skip ASR, load segments from this JSON file instead")
    parser.add_argument("--narrative-only", type=Path, default=None,
                        help="skip ASR+diarization+extraction, regenerate narrative from this pipeline.json")
    args = parser.parse_args()

    openrouter_key, _dashscope_key, groq_key = load_keys()

    if args.narrative_only:
        from scripts.narrative_agent import generate_narrative_v3
        loaded = json.loads(args.narrative_only.read_text())
        segments = loaded["segments"]
        claims = loaded["claims"]
        out_path = args.out or args.narrative_only
        ckpt_path = out_path.with_suffix(".narr_ckpt.json")
        print(f"[Narrative-only] Loaded {len(segments)} segments, {len(claims)} fragments from {args.narrative_only}", flush=True)
        narrative = generate_narrative_v3(claims, segments, openrouter_key, checkpoint_path=ckpt_path)
        loaded["narrative"] = narrative
        out_path.write_text(json.dumps(loaded, ensure_ascii=False, indent=2))
        print(f"\n[Done] Narrative written → {out_path}")
        for ch in narrative.get("chapters", []):
            body = ch.get("body", "")
            if body:
                print(f"\n## {ch['title']} ({len(body)} 字)")
                print(body[:600])
                if len(body) > 600:
                    print("  ...")
                if len(body) > 500:
                    print("  ...")
        return

    if args.skip_asr:
        print(f"[ASR] Skipping — loading segments from {args.skip_asr}", flush=True)
        loaded = json.loads(args.skip_asr.read_text())
        # Accept either a bare segments list or a full pipeline JSON
        segments = loaded["segments"] if isinstance(loaded, dict) else loaded
    else:
        if not args.audio.exists():
            print(f"Error: {args.audio} not found", file=sys.stderr)
            sys.exit(1)
        if not groq_key:
            print("Error: Groq API key not found. Add it to api_key file (line 3).", file=sys.stderr)
            sys.exit(1)
        segments = transcribe(args.audio, groq_key)
        segments = diarize_segments(segments, args.audio)

    out_path = args.out or Path(str(args.audio).replace(".mp3", "")).with_suffix(".pipeline.json")

    extraction_ckpt = out_path.with_suffix(".extraction_ckpt.json")
    claims = extract_claims(segments, openrouter_key, checkpoint_path=extraction_ckpt)

    # Save checkpoint after extraction so a narrative failure doesn't lose everything
    checkpoint = {"audio_file": str(args.audio), "segments": segments, "claims": claims, "narrative": {}}
    out_path.write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2))
    print(f"[Checkpoint] Saved after extraction → {out_path}", flush=True)

    narrative = generate_narrative(claims, segments, openrouter_key)

    output = {
        "audio_file": str(args.audio),
        "segments": segments,
        "claims": claims,
        "narrative": narrative,
    }
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    print(f"\n[Done] Full output → {out_path}")

    print("\n" + "=" * 60)
    print("NARRATIVE PREVIEW")
    print("=" * 60)
    for ch in narrative.get("chapters", []):
        body = ch.get("body", "")
        if body and "等待" not in body:
            print(f"\n## {ch['title']}")
            print(body[:500])
            if len(body) > 500:
                print("  ...")


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "packages"))
    sys.path.insert(0, str(ROOT / "apps/api"))
    main()
