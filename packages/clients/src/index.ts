import type {
  ApiEnvelope,
  AdminProjectDetail,
  AiCost,
  AdminSession,
  AlertRecord,
  AuthSession,
  AudioChunkPresignResult,
  AudioChunkUploadResult,
  Claim,
  ClaimCorrection,
  CorrectionAction,
  ConsentMethod,
  ConsentRecord,
  ConsentType,
  DeletionRequest,
  DraftResult,
  FamilyComment,
  Feedback,
  HouseholdOpsExport,
  InternalNote,
  InterviewSession,
  LogoutResult,
  ManualIntervention,
  PilotMetrics,
  PhotoCompleteResult,
  PhotoAnalysis,
  PhotoDeleteResult,
  PhotoPresignResult,
  PhotoRecord,
  ProjectCreateRequest,
  ProjectCreateResult,
  ProjectExport,
  ProjectPatchRequest,
  ProjectSummary,
  ProjectStatusResult,
  RetryTaskResult,
  SensitiveClaimReview,
  SessionRecovery,
  StoryPage,
  StoryShareLink,
  SupportTicket,
  VerificationIssue,
  VerificationResult,
  WxLoginRequest,
} from "@changjuan/shared-types";

export class ChangjuanClient {
  constructor(
    private readonly baseUrl: string,
    private readonly token?: string,
  ) {}

  async wxLogin(payload: WxLoginRequest): Promise<AuthSession> {
    const response = await this.request<ApiEnvelope<AuthSession>>(
      "/api/v1/auth/wx-login",
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
    );
    return response.data;
  }

  async refresh(): Promise<Pick<AuthSession, "access_token" | "refresh_token">> {
    const response = await this.request<ApiEnvelope<Pick<AuthSession, "access_token" | "refresh_token">>>(
      "/api/v1/auth/refresh",
      { method: "POST" },
    );
    return response.data;
  }

  async logout(): Promise<LogoutResult> {
    const response = await this.request<ApiEnvelope<LogoutResult>>(
      "/api/v1/auth/logout",
      { method: "POST" },
    );
    return response.data;
  }

  async createProject(project: ProjectCreateRequest): Promise<ProjectCreateResult> {
    const response = await this.request<ApiEnvelope<ProjectCreateResult>>(
      "/api/v1/projects",
      {
        method: "POST",
        body: JSON.stringify(project),
      },
    );
    return response.data;
  }

  async projects(): Promise<ProjectSummary[]> {
    const response = await this.request<ApiEnvelope<{ projects: ProjectSummary[] }>>("/api/v1/projects");
    return response.data.projects;
  }

  async project(projectId: string): Promise<ProjectSummary> {
    const response = await this.request<ApiEnvelope<ProjectSummary>>(`/api/v1/projects/${projectId}`);
    return response.data;
  }

  async updateProject(projectId: string, patch: ProjectPatchRequest): Promise<ProjectSummary> {
    const response = await this.request<ApiEnvelope<ProjectSummary>>(
      `/api/v1/projects/${projectId}`,
      {
        method: "PATCH",
        body: JSON.stringify(patch),
      },
    );
    return response.data;
  }

  async deleteProject(projectId: string): Promise<DeletionRequest> {
    const response = await this.request<ApiEnvelope<DeletionRequest>>(
      `/api/v1/projects/${projectId}`,
      { method: "DELETE" },
    );
    return response.data;
  }

  async presignPhoto(
    projectId: string,
    photo: { filename: string; contentType: string },
  ): Promise<PhotoPresignResult> {
    const response = await this.request<ApiEnvelope<PhotoPresignResult>>(
      `/api/v1/projects/${projectId}/photos/presign`,
      {
        method: "POST",
        body: JSON.stringify({ filename: photo.filename, content_type: photo.contentType }),
      },
    );
    return response.data;
  }

  async completePhoto(
    projectId: string,
    photo: { ossKey: string; caption?: string | null },
  ): Promise<PhotoCompleteResult> {
    const response = await this.request<ApiEnvelope<PhotoCompleteResult>>(
      `/api/v1/projects/${projectId}/photos/complete`,
      {
        method: "POST",
        body: JSON.stringify({ oss_key: photo.ossKey, caption: photo.caption }),
      },
    );
    return response.data;
  }

  async photos(projectId: string): Promise<PhotoRecord[]> {
    const response = await this.request<ApiEnvelope<{ photos: PhotoRecord[] }>>(
      `/api/v1/projects/${projectId}/photos`,
    );
    return response.data.photos;
  }

  async deletePhoto(photoId: string): Promise<PhotoDeleteResult> {
    const response = await this.request<ApiEnvelope<PhotoDeleteResult>>(
      `/api/v1/photos/${photoId}`,
      { method: "DELETE" },
    );
    return response.data;
  }

  async createInterviewSession(projectId: string): Promise<InterviewSession> {
    const response = await this.request<ApiEnvelope<InterviewSession>>(
      `/api/v1/projects/${projectId}/interview-sessions`,
      { method: "POST" },
    );
    return response.data;
  }

  async interviewSession(sessionId: string): Promise<InterviewSession> {
    const response = await this.request<ApiEnvelope<InterviewSession>>(
      `/api/v1/interview-sessions/${sessionId}`,
    );
    return response.data;
  }

  async startInterviewSession(sessionId: string): Promise<InterviewSession> {
    const response = await this.request<ApiEnvelope<InterviewSession>>(
      `/api/v1/interview-sessions/${sessionId}/start`,
      { method: "POST" },
    );
    return response.data;
  }

  async endInterviewSession(
    sessionId: string,
    status: InterviewSession["status"] = "completed",
  ): Promise<InterviewSession> {
    const response = await this.request<ApiEnvelope<InterviewSession>>(
      `/api/v1/interview-sessions/${sessionId}/end`,
      {
        method: "POST",
        body: JSON.stringify({ status }),
      },
    );
    return response.data;
  }

  interviewSessionStreamUrl(sessionId: string): string {
    const wsBaseUrl = this.baseUrl.replace(/^http:/, "ws:").replace(/^https:/, "wss:");
    return `${wsBaseUrl}/api/v1/interview-sessions/${sessionId}/stream`;
  }

  async pendingCorrections(projectId: string): Promise<Claim[]> {
    const response = await this.request<ApiEnvelope<{ claims: Claim[] }>>(
      `/api/v1/projects/${projectId}/corrections/pending`,
    );
    return response.data.claims;
  }

  async claim(claimId: string): Promise<Claim> {
    const response = await this.request<ApiEnvelope<Claim>>(`/api/v1/claims/${claimId}`);
    return response.data;
  }

  async correctClaim(
    claimId: string,
    correction: { action: CorrectionAction; modifiedText?: string; comment?: string },
  ): Promise<Claim> {
    const response = await this.request<ApiEnvelope<Claim>>(
      `/api/v1/claims/${claimId}/corrections`,
      {
        method: "POST",
        body: JSON.stringify({
          action: correction.action,
          modified_text: correction.modifiedText,
          comment: correction.comment,
        }),
      },
    );
    return response.data;
  }

  async completeCorrections(projectId: string): Promise<ProjectStatusResult> {
    const response = await this.request<ApiEnvelope<ProjectStatusResult>>(
      `/api/v1/projects/${projectId}/corrections/complete`,
      { method: "POST" },
    );
    return response.data;
  }

  async generateDraft(projectId: string): Promise<DraftResult> {
    const response = await this.request<ApiEnvelope<DraftResult>>(
      `/api/v1/projects/${projectId}/drafts/generate`,
      { method: "POST" },
    );
    return response.data;
  }

  async drafts(projectId: string): Promise<DraftResult> {
    const response = await this.request<ApiEnvelope<DraftResult>>(
      `/api/v1/projects/${projectId}/drafts`,
    );
    return response.data;
  }

  async verifyProject(projectId: string): Promise<VerificationResult> {
    const response = await this.request<ApiEnvelope<VerificationResult>>(
      `/api/v1/projects/${projectId}/verify`,
      { method: "POST" },
    );
    return response.data;
  }

  async requestSecondConsent(projectId: string): Promise<ProjectStatusResult> {
    const response = await this.request<ApiEnvelope<ProjectStatusResult>>(
      `/api/v1/projects/${projectId}/request-second-consent`,
      { method: "POST" },
    );
    return response.data;
  }

  async publishProject(projectId: string): Promise<ProjectStatusResult> {
    const response = await this.request<ApiEnvelope<ProjectStatusResult>>(
      `/api/v1/projects/${projectId}/publish`,
      { method: "POST" },
    );
    return response.data;
  }

  async adminLogin(email: string, password: string): Promise<AdminSession> {
    const response = await this.request<ApiEnvelope<AdminSession>>(
      "/api/v1/admin/auth/login",
      {
        method: "POST",
        body: JSON.stringify({ email, password }),
      },
    );
    return response.data;
  }

  async adminProjects(): Promise<ProjectSummary[]> {
    const response = await this.request<ApiEnvelope<{ projects: ProjectSummary[] }>>(
      "/api/v1/admin/projects",
    );
    return response.data.projects;
  }

  async adminProject(projectId: string): Promise<AdminProjectDetail> {
    const response = await this.request<ApiEnvelope<AdminProjectDetail>>(
      `/api/v1/admin/projects/${projectId}`,
    );
    return response.data;
  }

  async createAdminNote(
    projectId: string,
    note: { body: string; noteType?: string },
  ): Promise<InternalNote> {
    const response = await this.request<ApiEnvelope<InternalNote>>(
      `/api/v1/admin/projects/${projectId}/notes`,
      {
        method: "POST",
        body: JSON.stringify({ body: note.body, note_type: note.noteType }),
      },
    );
    return response.data;
  }

  async markManualPayment(
    projectId: string,
    payment: {
      paymentCents: number;
      paymentMethod: "manual_wechat" | "manual_alipay" | "waived" | "free_trial";
      paymentReference?: string;
    },
  ): Promise<ProjectSummary> {
    const response = await this.request<ApiEnvelope<ProjectSummary>>(
      `/api/v1/admin/projects/${projectId}/mark-payment`,
      {
        method: "POST",
        body: JSON.stringify({
          payment_cents: payment.paymentCents,
          payment_method: payment.paymentMethod,
          payment_reference: payment.paymentReference,
        }),
      },
    );
    return response.data;
  }

  async resolveVerificationIssue(issueId: string, resolutionReason: string): Promise<VerificationIssue> {
    const response = await this.request<ApiEnvelope<VerificationIssue>>(
      `/api/v1/admin/verification-issues/${issueId}/resolve`,
      {
        method: "POST",
        body: JSON.stringify({ resolution_reason: resolutionReason }),
      },
    );
    return response.data;
  }

  async pilotMetrics(): Promise<PilotMetrics> {
    const response = await this.request<ApiEnvelope<PilotMetrics>>("/api/v1/admin/metrics/pilot");
    return response.data;
  }

  async createFeedback(
    projectId: string,
    feedback: { npsScore?: number; recommend?: boolean; issueType?: string; body?: string },
  ): Promise<Feedback> {
    const response = await this.request<ApiEnvelope<Feedback>>(
      `/api/v1/projects/${projectId}/feedback`,
      {
        method: "POST",
        body: JSON.stringify({
          nps_score: feedback.npsScore,
          recommend: feedback.recommend,
          issue_type: feedback.issueType,
          body: feedback.body,
        }),
      },
    );
    return response.data;
  }

  async createSupportTicket(
    projectId: string,
    ticket: { category: string; body: string; priority?: "P0" | "P1" | "P2" },
  ): Promise<SupportTicket> {
    const response = await this.request<ApiEnvelope<SupportTicket>>(
      `/api/v1/projects/${projectId}/support-tickets`,
      {
        method: "POST",
        body: JSON.stringify(ticket),
      },
    );
    return response.data;
  }

  async supportTickets(): Promise<SupportTicket[]> {
    const response = await this.request<ApiEnvelope<{ support_tickets: SupportTicket[] }>>(
      "/api/v1/admin/support-tickets",
    );
    return response.data.support_tickets;
  }

  async patchSupportTicket(
    ticketId: string,
    patch: { status?: SupportTicket["status"]; priority?: SupportTicket["priority"]; adminOwnerId?: string },
  ): Promise<SupportTicket> {
    const response = await this.request<ApiEnvelope<SupportTicket>>(
      `/api/v1/admin/support-tickets/${ticketId}`,
      {
        method: "PATCH",
        body: JSON.stringify({
          status: patch.status,
          priority: patch.priority,
          admin_owner_id: patch.adminOwnerId,
        }),
      },
    );
    return response.data;
  }

  async householdOpsExport(): Promise<HouseholdOpsExport> {
    const response = await this.request<ApiEnvelope<HouseholdOpsExport>>(
      "/api/v1/admin/exports/household-ops",
    );
    return response.data;
  }

  async stuckProjects(): Promise<ProjectSummary[]> {
    const response = await this.request<ApiEnvelope<{ projects: ProjectSummary[] }>>(
      "/api/v1/admin/stuck-projects",
    );
    return response.data.projects;
  }

  async assignStuckProject(projectId: string, ownerId: string, reason: string): Promise<ProjectSummary> {
    const response = await this.request<ApiEnvelope<ProjectSummary>>(
      `/api/v1/admin/projects/${projectId}/stuck`,
      {
        method: "POST",
        body: JSON.stringify({ owner_id: ownerId, reason }),
      },
    );
    return response.data;
  }

  async recordManualIntervention(
    projectId: string,
    intervention: { category: string; minutes: number; body?: string },
  ): Promise<ManualIntervention> {
    const response = await this.request<ApiEnvelope<ManualIntervention>>(
      `/api/v1/admin/projects/${projectId}/manual-interventions`,
      {
        method: "POST",
        body: JSON.stringify(intervention),
      },
    );
    return response.data;
  }

  async recordAiCost(
    projectId: string,
    cost: { taskType: string; provider: string; costCents: number; generationRunId?: string },
  ): Promise<AiCost> {
    const response = await this.request<ApiEnvelope<AiCost>>(
      `/api/v1/admin/projects/${projectId}/ai-costs`,
      {
        method: "POST",
        body: JSON.stringify({
          task_type: cost.taskType,
          provider: cost.provider,
          cost_cents: cost.costCents,
          generation_run_id: cost.generationRunId,
        }),
      },
    );
    return response.data;
  }

  async sensitiveClaims(): Promise<SensitiveClaimReview[]> {
    const response = await this.request<ApiEnvelope<{ claims: SensitiveClaimReview[] }>>(
      "/api/v1/admin/sensitive-claims",
    );
    return response.data.claims;
  }

  async reviewSensitiveClaim(claimId: string, resolutionReason: string): Promise<SensitiveClaimReview> {
    const response = await this.request<ApiEnvelope<SensitiveClaimReview>>(
      `/api/v1/admin/claims/${claimId}/sensitive-review`,
      {
        method: "POST",
        body: JSON.stringify({ resolution_reason: resolutionReason }),
      },
    );
    return response.data;
  }

  async createPhotoAnalysis(
    photoId: string,
    analysis: { hypothesisText: string; confidence: number },
  ): Promise<PhotoAnalysis> {
    const response = await this.request<ApiEnvelope<PhotoAnalysis>>(
      `/api/v1/admin/photos/${photoId}/analysis`,
      {
        method: "POST",
        body: JSON.stringify({
          hypothesis_text: analysis.hypothesisText,
          confidence: analysis.confidence,
        }),
      },
    );
    return response.data;
  }

  async photoAnalyses(projectId: string): Promise<PhotoAnalysis[]> {
    const response = await this.request<ApiEnvelope<{ photo_analyses: PhotoAnalysis[] }>>(
      `/api/v1/admin/projects/${projectId}/photo-analyses`,
    );
    return response.data.photo_analyses;
  }

  async convertPhotoAnalysisToCorrectionCandidate(
    analysisId: string,
  ): Promise<{ photo_analysis: PhotoAnalysis; claim: Claim }> {
    const response = await this.request<ApiEnvelope<{ photo_analysis: PhotoAnalysis; claim: Claim }>>(
      `/api/v1/admin/photo-analyses/${analysisId}/correction-candidate`,
      { method: "POST" },
    );
    return response.data;
  }

  async claimCorrections(claimId: string): Promise<ClaimCorrection[]> {
    const response = await this.request<ApiEnvelope<{ corrections: ClaimCorrection[] }>>(
      `/api/v1/claims/${claimId}/corrections`,
    );
    return response.data.corrections;
  }

  async alerts(): Promise<AlertRecord[]> {
    const response = await this.request<ApiEnvelope<{ alerts: AlertRecord[] }>>(
      "/api/v1/admin/alerts",
    );
    return response.data.alerts;
  }

  async simulateAlert(): Promise<void> {
    await this.request<ApiEnvelope<Record<string, never>>>(
      "/api/v1/admin/alerts/simulate-500",
      { method: "POST" },
    );
  }

  async retryTask(taskId: string): Promise<RetryTaskResult> {
    const response = await this.request<ApiEnvelope<RetryTaskResult>>(
      `/api/v1/admin/tasks/${taskId}/retry`,
      { method: "POST" },
    );
    return response.data;
  }

  async deletionRequest(projectId: string): Promise<DeletionRequest> {
    const response = await this.request<ApiEnvelope<DeletionRequest>>(
      `/api/v1/projects/${projectId}/deletion-request`,
    );
    return response.data;
  }

  async projectExport(projectId: string): Promise<ProjectExport> {
    const response = await this.request<ApiEnvelope<ProjectExport>>(
      `/api/v1/projects/${projectId}/export`,
    );
    return response.data;
  }

  async createConsent(
    projectId: string,
    consent: { consentType: ConsentType; method?: ConsentMethod; evidenceOssKey?: string },
  ): Promise<ConsentRecord> {
    const response = await this.request<ApiEnvelope<ConsentRecord>>(
      `/api/v1/projects/${projectId}/consents`,
      {
        method: "POST",
        body: JSON.stringify({
          consent_type: consent.consentType,
          method: consent.method,
          evidence_oss_key: consent.evidenceOssKey,
        }),
      },
    );
    return response.data;
  }

  async withdrawConsent(projectId: string, consentId: string): Promise<ConsentRecord> {
    const response = await this.request<ApiEnvelope<ConsentRecord>>(
      `/api/v1/projects/${projectId}/consents/${consentId}/withdraw`,
      { method: "POST" },
    );
    return response.data;
  }

  async uploadAudioChunk(
    sessionId: string,
    chunk: {
      sequenceNumber: number;
      durationMs: number;
      ossKey: string;
      partialTranscript?: string;
      transcriptConfidence?: number;
      speaker?: "storyteller" | "interviewer";
    },
  ): Promise<AudioChunkUploadResult> {
    const response = await this.request<ApiEnvelope<AudioChunkUploadResult>>(
      `/api/v1/interview-sessions/${sessionId}/audio-chunks`,
      {
        method: "POST",
        body: JSON.stringify({
          sequence_number: chunk.sequenceNumber,
          duration_ms: chunk.durationMs,
          oss_key: chunk.ossKey,
          partial_transcript: chunk.partialTranscript,
          transcript_confidence: chunk.transcriptConfidence,
          speaker: chunk.speaker,
        }),
      },
    );
    return response.data;
  }

  async presignAudioChunk(
    sessionId: string,
    chunk: { sequenceNumber: number; contentType?: string },
  ): Promise<AudioChunkPresignResult> {
    const response = await this.request<ApiEnvelope<AudioChunkPresignResult>>(
      `/api/v1/interview-sessions/${sessionId}/audio-chunks/presign`,
      {
        method: "POST",
        body: JSON.stringify({
          sequence_number: chunk.sequenceNumber,
          content_type: chunk.contentType ?? "audio/mpeg",
        }),
      },
    );
    return response.data;
  }

  async sessionRecovery(sessionId: string): Promise<SessionRecovery> {
    const response = await this.request<ApiEnvelope<SessionRecovery>>(
      `/api/v1/interview-sessions/${sessionId}/recovery`,
    );
    return response.data;
  }

  async storyPage(
    storyPageId: string,
    access: { shareToken: string; password?: string } | null = null,
  ): Promise<StoryPage> {
    const params = new URLSearchParams();
    if (access?.shareToken) {
      params.set("share_token", access.shareToken);
    }
    if (access?.password) {
      params.set("password", access.password);
    }
    const query = params.toString();
    const response = await this.request<ApiEnvelope<StoryPage>>(
      `/api/v1/story-pages/${storyPageId}${query ? `?${query}` : ""}`,
    );
    return response.data;
  }

  async createStoryShareLink(storyPageId: string, password?: string): Promise<StoryShareLink> {
    const response = await this.request<ApiEnvelope<StoryShareLink>>(
      `/api/v1/story-pages/${storyPageId}/share-links`,
      {
        method: "POST",
        body: JSON.stringify(password ? { password } : {}),
      },
    );
    return response.data;
  }

  async revokeStoryShareLink(storyPageId: string, shareLinkId: string): Promise<StoryShareLink> {
    const response = await this.request<ApiEnvelope<StoryShareLink>>(
      `/api/v1/story-pages/${storyPageId}/share-links/${shareLinkId}`,
      { method: "DELETE" },
    );
    return response.data;
  }

  async resetStoryShareLink(storyPageId: string, shareLinkId: string): Promise<StoryShareLink> {
    const response = await this.request<ApiEnvelope<StoryShareLink>>(
      `/api/v1/story-pages/${storyPageId}/share-links/${shareLinkId}/reset`,
      { method: "POST" },
    );
    return response.data;
  }

  async createStoryComment(
    storyPageId: string,
    comment: {
      shareToken: string;
      displayName: string;
      body: string;
      password?: string;
    },
  ): Promise<FamilyComment> {
    const response = await this.request<ApiEnvelope<FamilyComment>>(
      `/api/v1/story-pages/${storyPageId}/comments`,
      {
        method: "POST",
        body: JSON.stringify({
          share_token: comment.shareToken,
          password: comment.password,
          display_name: comment.displayName,
          body: comment.body,
        }),
      },
    );
    return response.data;
  }

  async exportStoryPdf(
    storyPageId: string,
    access: { shareToken: string; password?: string } | null = null,
  ): Promise<Blob> {
    const params = new URLSearchParams();
    if (access?.shareToken) {
      params.set("share_token", access.shareToken);
    }
    if (access?.password) {
      params.set("password", access.password);
    }
    const query = params.toString();
    const headers = new Headers();
    if (this.token) {
      headers.set("Authorization", `Bearer ${this.token}`);
    }
    const response = await fetch(
      `${this.baseUrl}/api/v1/story-pages/${storyPageId}/pdf-export${query ? `?${query}` : ""}`,
      { method: "POST", headers },
    );
    if (!response.ok) {
      const body = (await response.json()) as ApiEnvelope<unknown>;
      throw new Error(body.message);
    }
    return response.blob();
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const headers = new Headers(init.headers);
    headers.set("Content-Type", "application/json");
    if (this.token) {
      headers.set("Authorization", `Bearer ${this.token}`);
    }
    const response = await fetch(`${this.baseUrl}${path}`, { ...init, headers });
    const body = (await response.json()) as ApiEnvelope<unknown>;
    if (!response.ok || body.code !== 0) {
      throw new Error(body.message);
    }
    return body as T;
  }
}
