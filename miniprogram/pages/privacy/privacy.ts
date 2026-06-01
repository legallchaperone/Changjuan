import { request } from "../../utils/api";

type ProjectExportResponse = {
  project: {
    title: string;
    status: string;
  };
  claims: unknown[];
  photos: unknown[];
  consents: unknown[];
  pdf_exports: unknown[];
};

type DeletionRequestResponse = {
  deletion_request_id: string;
  status: string;
  execute_after_at: string;
};

Page({
  data: {
    projectId: "",
    loading: false,
    errorMessage: "",
    exportSummary: "",
    deletionRequestId: "",
    deletionStatus: "",
    executeAfterAt: ""
  },
  onLoad(options: Record<string, string | undefined>) {
    if (options.project_id) {
      this.setData({ projectId: options.project_id });
    }
  },
  onProjectId(event: WechatMiniprogram.Input) {
    this.setData({ projectId: event.detail.value });
  },
  async exportProject() {
    if (!this.ensureProjectId()) return;
    this.setData({ loading: true, errorMessage: "" });
    try {
      const data = await request<ProjectExportResponse>(
        `/api/v1/projects/${this.data.projectId}/export`,
        "GET"
      );
      this.setData({
        loading: false,
        exportSummary: `${data.project.title} / ${data.project.status} / claims ${data.claims.length} / photos ${data.photos.length} / consents ${data.consents.length} / pdf ${data.pdf_exports.length}`
      });
    } catch (error) {
      this.setData({ loading: false, errorMessage: (error as Error).message });
    }
  },
  requestDeletion() {
    if (!this.ensureProjectId()) return;
    wx.showModal({
      title: "确认删除",
      content: "删除后项目会立即不可见，并在 T+7 物理清理资源。",
      confirmText: "删除",
      confirmColor: "#a5453d",
      success: (result) => {
        if (result.confirm) {
          void this.performDeletion();
        }
      }
    });
  },
  async performDeletion() {
    this.setData({ loading: true, errorMessage: "" });
    try {
      const data = await request<DeletionRequestResponse>(
        `/api/v1/projects/${this.data.projectId}`,
        "DELETE"
      );
      this.setDeletionStatus(data);
    } catch (error) {
      this.setData({ loading: false, errorMessage: (error as Error).message });
    }
  },
  async checkDeletionStatus() {
    if (!this.ensureProjectId()) return;
    this.setData({ loading: true, errorMessage: "" });
    try {
      const data = await request<DeletionRequestResponse>(
        `/api/v1/projects/${this.data.projectId}/deletion-request`,
        "GET"
      );
      this.setDeletionStatus(data);
    } catch (error) {
      this.setData({ loading: false, errorMessage: (error as Error).message });
    }
  },
  setDeletionStatus(data: DeletionRequestResponse) {
    this.setData({
      loading: false,
      deletionRequestId: data.deletion_request_id,
      deletionStatus: data.status,
      executeAfterAt: data.execute_after_at
    });
  },
  ensureProjectId() {
    if (this.data.projectId) return true;
    this.setData({ errorMessage: "请先填写 project_id" });
    return false;
  }
});
