import { request } from "../../utils/api";

type ClaimPriority = "P0" | "P1" | "P2";
type CorrectionAction = "confirm" | "modify" | "unsure" | "hide_from_family" | "delete";

type CorrectionClaim = {
  id: string;
  claim_text: string;
  claim_priority: ClaimPriority;
  modified_text?: string | null;
};

type PendingCorrectionsResponse = {
  claims: CorrectionClaim[];
};

type CorrectionPayload = {
  action: CorrectionAction;
  modified_text?: string;
};

const priorityRank: Record<ClaimPriority, number> = { P0: 0, P1: 1, P2: 2 };

Page({
  data: {
    projectId: "",
    pendingLimit: 20,
    claims: [] as CorrectionClaim[],
    modifiedTextById: {} as Record<string, string>,
    loading: false,
    errorMessage: ""
  },
  onLoad(options: Record<string, string | undefined>) {
    if (options.project_id) {
      this.setData({ projectId: options.project_id });
      void this.loadClaims();
    }
  },
  async loadClaims() {
    if (!this.data.projectId) return;
    this.setData({ loading: true, errorMessage: "" });
    try {
      const data = await request<PendingCorrectionsResponse>(
        `/api/v1/projects/${this.data.projectId}/corrections/pending`,
        "GET"
      );
      this.setData({
        claims: this.sortClaims(data.claims).slice(0, this.data.pendingLimit),
        loading: false
      });
    } catch (error) {
      this.setData({ loading: false, errorMessage: (error as Error).message });
    }
  },
  sortClaims(claims: CorrectionClaim[]) {
    return [...claims].sort((left, right) => priorityRank[left.claim_priority] - priorityRank[right.claim_priority]);
  },
  onModifiedText(event: WechatMiniprogram.Input) {
    const claimId = String(event.currentTarget.dataset.id || "");
    this.setData({ [`modifiedTextById.${claimId}`]: event.detail.value });
  },
  confirm(event: WechatMiniprogram.TouchEvent) {
    const claimId = claimIdFromEvent(event);
    void this.applyCorrection(claimId, { action: "confirm" });
  },
  modify(event: WechatMiniprogram.TouchEvent) {
    const claimId = claimIdFromEvent(event);
    const modifiedText = this.data.modifiedTextById[claimId] || "";
    void this.applyCorrection(claimId, { action: "modify", modified_text: modifiedText });
  },
  unsure(event: WechatMiniprogram.TouchEvent) {
    const claimId = claimIdFromEvent(event);
    void this.applyCorrection(claimId, { action: "unsure" });
  },
  hide(event: WechatMiniprogram.TouchEvent) {
    const claimId = claimIdFromEvent(event);
    void this.applyCorrection(claimId, { action: "hide_from_family" });
  },
  deleteClaim(event: WechatMiniprogram.TouchEvent) {
    const claimId = claimIdFromEvent(event);
    void this.applyCorrection(claimId, { action: "delete" });
  },
  async applyCorrection(claimId: string, payload: CorrectionPayload) {
    if (!claimId) return;
    this.setData({ loading: true, errorMessage: "" });
    try {
      await request<CorrectionClaim>(`/api/v1/claims/${claimId}/corrections`, "POST", payload);
      await this.loadClaims();
    } catch (error) {
      this.setData({ loading: false, errorMessage: (error as Error).message });
    }
  }
});

function claimIdFromEvent(event: WechatMiniprogram.TouchEvent): string {
  return String(event.currentTarget.dataset.id || "");
}
