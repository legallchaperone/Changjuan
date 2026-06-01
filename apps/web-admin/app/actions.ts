"use server";

import { ChangjuanClient } from "@changjuan/clients";

export type RetryTaskState = {
  status: "idle" | "queued" | "failed";
  message: string;
};

const initialRetryTaskState: RetryTaskState = { status: "idle", message: "" };

export async function retryTaskAction(
  _previousState: RetryTaskState = initialRetryTaskState,
  formData: FormData,
): Promise<RetryTaskState> {
  const taskId = String(formData.get("task_id") || "").trim();
  if (!taskId) {
    return { status: "failed", message: "请输入 task_id" };
  }
  if (!process.env.ADMIN_API_TOKEN) {
    return { status: "failed", message: "缺少 ADMIN_API_TOKEN，无法执行后台重试" };
  }

  try {
    const result = await createAdminClient().retryTask(taskId);
    return { status: "queued", message: `任务已入队 ${result.task_id}` };
  } catch (error) {
    return { status: "failed", message: (error as Error).message };
  }
}

function createAdminClient() {
  return new ChangjuanClient(adminApiBaseUrl(), process.env.ADMIN_API_TOKEN);
}

function adminApiBaseUrl() {
  return process.env.ADMIN_API_BASE_URL || process.env.API_BASE_URL || "http://localhost:8000";
}
