from __future__ import annotations

from pathlib import Path


def test_shared_types_include_soft_delete_and_deletion_request_contracts() -> None:
    shared_types = Path("packages/shared-types/src/index.ts").read_text()

    assert "deleted_at?: string | null" in shared_types
    assert "purge_after_at?: string | null" in shared_types
    assert "export type DeletionRequest" in shared_types
    assert "deletion_request_id: string" in shared_types
    assert "execute_after_at: string" in shared_types


def test_shared_types_and_client_include_auth_contracts() -> None:
    shared_types = Path("packages/shared-types/src/index.ts").read_text()
    client = Path("packages/clients/src/index.ts").read_text()

    assert "export type WxLoginRequest" in shared_types
    assert "export type AuthSession" in shared_types
    assert "access_token: string" in shared_types
    assert "export type LogoutResult" in shared_types
    assert "revoked: boolean" in shared_types
    assert "async wxLogin(" in client
    assert "async refresh(" in client
    assert "async logout(" in client


def test_shared_types_and_client_cover_phase1_api_surface() -> None:
    shared_types = Path("packages/shared-types/src/index.ts").read_text()
    client = Path("packages/clients/src/index.ts").read_text()

    assert "wx_code?: string | null" in shared_types
    assert "wx_openid?: string | null" in shared_types

    for type_name in (
        "ProjectCreateRequest",
        "ProjectCreateResult",
        "ProjectPatchRequest",
        "PhotoPresignResult",
        "PhotoCompleteResult",
        "PhotoDeleteResult",
        "InterviewSession",
        "DraftResult",
        "VerificationIssue",
        "VerificationResult",
        "ProjectStatusResult",
        "AdminSession",
    ):
        assert f"export type {type_name}" in shared_types

    for method_name in (
        "createProject",
        "project",
        "updateProject",
        "deleteProject",
        "presignPhoto",
        "completePhoto",
        "photos",
        "deletePhoto",
        "createInterviewSession",
        "interviewSession",
        "startInterviewSession",
        "endInterviewSession",
        "interviewSessionStreamUrl",
        "pendingCorrections",
        "claim",
        "correctClaim",
        "completeCorrections",
        "generateDraft",
        "drafts",
        "verifyProject",
        "requestSecondConsent",
        "publishProject",
        "adminLogin",
        "createAdminNote",
        "markManualPayment",
        "resolveVerificationIssue",
    ):
        assert f"async {method_name}(" in client or f"{method_name}(" in client

    for path in (
        "/api/v1/projects/${projectId}/photos/presign",
        "/api/v1/projects/${projectId}/photos/complete",
        "/api/v1/interview-sessions/${sessionId}/start",
        "/api/v1/projects/${projectId}/drafts/generate",
        "/api/v1/projects/${projectId}/request-second-consent",
        "/api/v1/admin/verification-issues/${issueId}/resolve",
    ):
        assert path in client


def test_shared_types_and_client_include_story_share_contracts() -> None:
    shared_types = Path("packages/shared-types/src/index.ts").read_text()
    client = Path("packages/clients/src/index.ts").read_text()

    assert "export type StoryShareLink" in shared_types
    assert "share_token: string | null" in shared_types
    assert "password_protected: boolean" in shared_types
    assert "export type StoryPage" in shared_types
    assert "audio_citations: AudioCitation[]" in shared_types
    assert "export type FamilyComment" in shared_types
    assert "async storyPage(" in client
    assert "async createStoryShareLink(" in client
    assert "async revokeStoryShareLink(" in client
    assert "async resetStoryShareLink(" in client
    assert "async createStoryComment(" in client
    assert "async exportStoryPdf(" in client


def test_shared_types_and_client_include_project_export_contract() -> None:
    shared_types = Path("packages/shared-types/src/index.ts").read_text()
    client = Path("packages/clients/src/index.ts").read_text()

    assert "export type ProjectExport" in shared_types
    assert "thumbnail_oss_key: string" in shared_types
    assert "consents: ConsentRecord[]" in shared_types
    assert "share_links: StoryShareLinkExport[]" in shared_types
    assert "family_comments: FamilyComment[]" in shared_types
    assert "export type PdfExportRecord" in shared_types
    assert "pdf_exports: PdfExportRecord[]" in shared_types
    assert "feedback: Feedback[]" in shared_types
    assert "support_tickets: SupportTicket[]" in shared_types
    assert "async projectExport(" in client


def test_shared_types_and_client_include_consent_withdrawal_contract() -> None:
    shared_types = Path("packages/shared-types/src/index.ts").read_text()
    client = Path("packages/clients/src/index.ts").read_text()

    assert "export type ConsentRecord" in shared_types
    assert "export type ConsentType" in shared_types
    assert "export type ConsentMethod" in shared_types
    assert "withdrawn_at: string | null" in shared_types
    assert "minimized_at: string | null" in shared_types
    assert "async createConsent(" in client
    assert "async withdrawConsent(" in client


def test_shared_types_and_client_include_session_recovery_contract() -> None:
    shared_types = Path("packages/shared-types/src/index.ts").read_text()
    client = Path("packages/clients/src/index.ts").read_text()

    assert "export type AudioChunkPresignResult" in shared_types
    assert "upload_url: string" in shared_types
    assert "headers: Record<string, string>" in shared_types
    assert "async presignAudioChunk(" in client
    assert "export type AudioChunkUploadResult" in shared_types
    assert "transcript_segment_id: string | null" in shared_types
    assert "export type TranscriptSegment" in shared_types
    assert "low_confidence_review: boolean" in shared_types
    assert "export type AdminProjectDetail" in shared_types
    assert "transcript_segments: TranscriptSegment[]" in shared_types
    assert "export type SessionRecovery" in shared_types
    assert "missing_sequence_numbers: number[]" in shared_types
    assert "async uploadAudioChunk(" in client
    assert "partialTranscript?: string" in client
    assert "async adminProject(" in client
    assert "async sessionRecovery(" in client


def test_shared_types_and_client_include_admin_ops_contracts() -> None:
    shared_types = Path("packages/shared-types/src/index.ts").read_text()
    client = Path("packages/clients/src/index.ts").read_text()

    assert "export type Feedback" in shared_types
    assert "export type HouseholdOpsExport" in shared_types
    assert "manual_intervention_count: number" in shared_types
    assert "ai_cost_cents: number" in shared_types
    assert "ops_owner_id?: string | null" in shared_types
    assert "async createFeedback(" in client
    assert "async householdOpsExport(" in client
    assert "async assignStuckProject(" in client
    assert "async recordManualIntervention(" in client
    assert "async recordAiCost(" in client


def test_shared_types_and_client_include_support_ticket_contracts() -> None:
    shared_types = Path("packages/shared-types/src/index.ts").read_text()
    client = Path("packages/clients/src/index.ts").read_text()

    assert "export type SupportTicket" in shared_types
    assert "ticket_id: string" in shared_types
    assert "admin_owner_id: string | null" in shared_types
    assert "async createSupportTicket(" in client
    assert "async supportTickets(" in client
    assert "async patchSupportTicket(" in client


def test_shared_types_and_client_include_sensitive_review_contracts() -> None:
    shared_types = Path("packages/shared-types/src/index.ts").read_text()
    client = Path("packages/clients/src/index.ts").read_text()

    assert "export type SensitiveClaimReview" in shared_types
    assert "human_reviewed: boolean" in shared_types
    assert "async sensitiveClaims(" in client
    assert "async reviewSensitiveClaim(" in client


def test_shared_types_and_client_include_photo_analysis_contracts() -> None:
    shared_types = Path("packages/shared-types/src/index.ts").read_text()
    client = Path("packages/clients/src/index.ts").read_text()

    assert "export type PhotoAnalysis" in shared_types
    assert "eligible_for_prompt: boolean" in shared_types
    assert "converted_claim_id: string | null" in shared_types
    assert "async createPhotoAnalysis(" in client
    assert "async photoAnalyses(" in client
    assert "async convertPhotoAnalysisToCorrectionCandidate(" in client


def test_shared_types_and_client_include_correction_history_contracts() -> None:
    shared_types = Path("packages/shared-types/src/index.ts").read_text()
    client = Path("packages/clients/src/index.ts").read_text()

    assert "export type ClaimCorrection" in shared_types
    assert "correction_id: string" in shared_types
    assert "async claimCorrections(" in client


def test_shared_types_and_client_include_alert_contracts() -> None:
    shared_types = Path("packages/shared-types/src/index.ts").read_text()
    client = Path("packages/clients/src/index.ts").read_text()

    assert "export type AlertRecord" in shared_types
    assert "error_type: string" in shared_types
    assert "async alerts(" in client
    assert "async simulateAlert(" in client
