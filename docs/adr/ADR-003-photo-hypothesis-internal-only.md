# ADR-003: Photo VLM is internal hypothesis only in Phase 1

Status: accepted.

Photo analysis is useful as an interview cue and correction candidate, but Phase 1 must not promise that AI can reliably identify old photos. VLM output is kept admin-only, marked as hypothesis, and must use uncertainty language such as "可能", "大约", or "推测".

Unconfirmed photo hypotheses never enter formal narrative text.
