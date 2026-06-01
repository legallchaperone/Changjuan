"use client";

import { RotateCcw } from "lucide-react";
import { useActionState } from "react";
import type { RetryTaskState } from "../app/actions";

type RetryTaskAction = (state: RetryTaskState, formData: FormData) => Promise<RetryTaskState>;

const initialState: RetryTaskState = { status: "idle", message: "" };

export function RetryTaskButton({
  action,
  defaultTaskId,
}: {
  action: RetryTaskAction;
  defaultTaskId: string;
}) {
  const [state, formAction, pending] = useActionState(action, initialState);
  const queued = state.status === "queued";
  return (
    <form action={formAction} className="retry-form">
      <input aria-label="task_id" name="task_id" defaultValue={defaultTaskId} />
      <button type="submit" aria-live="polite" disabled={pending} className={queued ? "queued" : undefined}>
        <RotateCcw size={16} /> {pending ? "提交中" : queued ? "任务已入队" : "重试失败任务"}
      </button>
      {state.message ? <span className={queued ? "form-status ok" : "form-status error"}>{state.message}</span> : null}
    </form>
  );
}
