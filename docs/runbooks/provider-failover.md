# Provider Failover Runbook

All provider calls go through `changjuan_core.providers.router.ProviderRouter`.

1. Confirm the task type in `TaskType`.
2. Inspect the related `generation_runs` record for `prompt_version`, `prompt_hash`, attempts, raw input key, and raw output key.
3. Primary providers are retried three times.
4. The fourth attempt switches to the configured backup provider.
5. If both providers fail, the worker leaves the task retryable and admin can call `/api/v1/admin/tasks/{task_id}/retry`.

Do not call providers directly from API, worker, admin, H5, or mini program code.
