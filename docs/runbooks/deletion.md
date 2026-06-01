# Deletion Runbook

Deletion requests are immediate from the user's perspective and delayed for physical purge.

1. Create `deletion_requests`.
2. Set `deleted_at = now()` and `purge_after_at = now() + 7 days` on all resource tables listed in `phase1.md`.
3. Hide deleted resources from user and admin product views immediately.
4. At T+7, worker purges database rows and OSS objects.
5. Keep `audit_logs`, `deletion_requests`, and minimized `consent_records`.

If legal hold applies, keep only hashes, timestamps, and operation records, not raw audio or photos.
