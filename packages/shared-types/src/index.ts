export type ApiEnvelope<T> = {
  code: number;
  data: T;
  message: string;
  trace_id: string;
};

export type WxLoginRequest = {
  wx_openid?: string | null;
  wx_code?: string | null;
  wx_unionid?: string | null;
  nickname?: string | null;
  avatar_url?: string | null;
  phone_e164?: string | null;
};

export type AuthSession = {
  access_token: string;
  refresh_token: string;
  user_id: string;
};

export type AdminSession = {
  access_token: string;
  admin_user_id: string;
};

export type LogoutResult = {
  revoked: boolean;
};

export type StorytellerInput = {
  display_name: string;
  relation_to_payer: string;
  birth_year?: number | null;
  birth_place?: string | null;
  current_city?: string | null;
  primary_dialect?: string | null;
};

export type ProjectCreateRequest = {
  storyteller: StorytellerInput;
  title: string;
  themes?: string[];
  tier?: string;
};

export type ProjectCreateResult = {
  project_id: string;
  status: "created";
  payment_required: boolean;
  payment_mode: "manual";
  payment_instruction: string;
  next_action: "complete_manual_deposit";
};

export type ProjectPatchRequest = {
  title?: string;
  themes?: string[];
};

export type ProjectStatus =
  | "created"
  | "payment_marked"
  | "interview_ready"
  | "interview_in_progress"
  | "interview_completed"
  | "claims_extracted"
  | "family_correction_pending"
  | "family_correction_completed"
  | "story_generated"
  | "verified"
  | "elder_second_consent_pending"
  | "published"
  | "deletion_requested";

export type ProjectSummary = {
  project_id: string;
  title: string;
  status: ProjectStatus;
  payment_status: "not_required" | "pending" | "paid" | "waived";
  payment_cents: number;
  storyteller: Record<string, string | number | null>;
  themes: string[];
  story_page_id: string | null;
  ops_owner_id?: string | null;
  stuck_reason?: string | null;
  stuck_at?: string | null;
  created_at: string;
  updated_at: string;
  deleted_at?: string | null;
  purge_after_at?: string | null;
};

export type ProjectStatusResult = {
  status: ProjectStatus;
};

export type PhotoPresignResult = {
  upload_url: string;
  oss_key: string;
  headers: Record<string, string>;
};

export type AudioChunkPresignResult = {
  upload_url: string;
  oss_key: string;
  headers: Record<string, string>;
};

export type PhotoCompleteResult = {
  photo_id: string;
  thumbnail_oss_key: string;
  photo_count: number;
  internal_photo_hypothesis_only: boolean;
};

export type PhotoDeleteResult = {
  deleted: boolean;
};

export type InterviewSessionStatus =
  | "scheduled"
  | "in_progress"
  | "completed"
  | "completed_short"
  | "aborted_by_storyteller"
  | "aborted_technical";

export type InterviewSession = {
  session_id: string;
  status: InterviewSessionStatus;
};

export type ClaimPriority = "P0" | "P1" | "P2";
export type ClaimVerificationStatus =
  | "pending"
  | "confirmed"
  | "modified"
  | "marked_unsure"
  | "hidden"
  | "deleted"
  | "rejected";

export type Claim = {
  id: string;
  claim_text: string;
  modified_text?: string | null;
  claim_type: string;
  claim_priority: ClaimPriority;
  source_segment_ids?: string[];
  confidence: number;
  support_status: "supported" | "unsupported" | "conflicting" | "needs_review";
  verification_status: ClaimVerificationStatus;
  sensitivity_level: "normal" | "sensitive" | "highly_sensitive";
  human_reviewed: boolean;
  embedding?: number[] | null;
  deleted_at?: string | null;
  purge_after_at?: string | null;
};

export type SensitiveClaimReview = Claim & {
  claim_id: string;
  project_id: string;
};

export type ClaimCorrection = {
  correction_id: string;
  claim_id: string;
  user_id: string;
  action: ClaimVerificationStatus | "confirm" | "modify" | "unsure" | "hide_from_family" | "delete";
  modified_text: string | null;
  comment: string | null;
  created_at: string;
};

export type CorrectionAction = "confirm" | "modify" | "unsure" | "hide_from_family" | "delete";

export type DraftResult = {
  story_page_id?: string;
  chapters: StoryChapter[];
};

export type VerificationIssue = {
  id: string;
  severity: "block" | "warn" | "info";
  gate?: string;
  message?: string;
  claim_id?: string | null;
  project_id?: string | null;
  resolved_at?: string | null;
  resolution_reason?: string | null;
  resolved_by_admin_id?: string | null;
};

export type VerificationResult = {
  issues: VerificationIssue[];
};

export type SessionRecovery = {
  session_id: string;
  last_accepted_sequence_number: number | null;
  missing_sequence_numbers: number[];
  buffered_chunk_count: number;
};

export type AudioChunkRecord = {
  session_id: string;
  sequence_number: number;
  duration_ms: number;
  oss_key: string;
  received_at: string;
  deleted_at: string | null;
  purge_after_at: string | null;
};

export type TranscriptSegment = {
  transcript_segment_id: string;
  project_id: string;
  session_id: string;
  audio_chunk_sequence_number: number;
  speaker: "storyteller" | "interviewer";
  text: string;
  start_ms: number;
  end_ms: number;
  confidence: number;
  low_confidence_review: boolean;
  created_at: string;
  deleted_at: string | null;
  purge_after_at: string | null;
};

export type AudioChunkUploadResult = {
  session_id: string;
  sequence_number: number;
  accepted: boolean;
  last_accepted_sequence_number: number | null;
  missing_sequence_numbers: number[];
  transcript_segment_id: string | null;
};

export type AudioCitation = {
  claim_id: string;
  segment_id: string;
  starts_at_ms: number;
  duration_ms: number;
  audio_url: string;
};

export type StoryChapter = {
  id: string;
  slug: string;
  title: string;
  body: string;
  claim_ids: string[];
  audio_citations: AudioCitation[];
};

export type FamilyComment = {
  comment_id: string;
  story_page_id: string;
  display_name: string;
  body: string;
  created_at: string;
};

export type StoryPage = {
  story_page_id: string;
  chapters: StoryChapter[];
  comments: FamilyComment[];
};

export type StoryShareLink = {
  share_link_id: string;
  story_page_id: string;
  enabled: boolean;
  password_protected: boolean;
  share_token: string | null;
  share_url: string | null;
  created_at: string;
  revoked_at: string | null;
  reset_at: string | null;
};

export type StoryShareLinkExport = {
  share_link_id: string;
  story_page_id: string;
  enabled: boolean;
  password_protected: boolean;
  created_at: string;
  revoked_at: string | null;
  reset_at: string | null;
};

export type ExportedStoryPage = StoryPage & {
  enabled: boolean;
  share_links_enabled: boolean;
};

export type PhotoRecord = {
  photo_id: string;
  project_id: string;
  oss_key: string;
  thumbnail_oss_key: string;
  caption: string | null;
  deleted_at: string | null;
  purge_after_at: string | null;
};

export type PhotoAnalysis = {
  photo_analysis_id: string;
  project_id: string;
  photo_id: string;
  hypothesis_text: string;
  confidence: number;
  internal_only: boolean;
  eligible_for_prompt: boolean;
  converted_claim_id: string | null;
  created_at: string;
  deleted_at: string | null;
  purge_after_at: string | null;
};

export type PdfExportRecord = {
  pdf_export_id: string;
  project_id: string;
  story_page_id: string;
  oss_key: string;
  created_at: string;
  deleted_at: string | null;
  purge_after_at: string | null;
};

export type ConsentType = "interview_consent" | "family_sharing";
export type ConsentMethod = "text" | "audio";

export type ConsentRecord = {
  consent_id: string;
  project_id: string;
  user_id: string | null;
  consent_type: ConsentType;
  method: ConsentMethod;
  evidence_oss_key: string | null;
  withdrawn_at: string | null;
  minimized_at: string | null;
  created_at: string;
};

export type ProjectExport = {
  project: ProjectSummary;
  photos: PhotoRecord[];
  claims: Claim[];
  audio_chunks: AudioChunkRecord[];
  transcript_segments: TranscriptSegment[];
  consents: ConsentRecord[];
  story_page: ExportedStoryPage | null;
  share_links: StoryShareLinkExport[];
  family_comments: FamilyComment[];
  pdf_exports: PdfExportRecord[];
  feedback: Feedback[];
  support_tickets: SupportTicket[];
};

export type Feedback = {
  feedback_id: string;
  project_id: string;
  user_id: string;
  nps_score: number | null;
  recommend: boolean | null;
  issue_type: string | null;
  body: string | null;
  created_at: string;
};

export type SupportTicket = {
  ticket_id: string;
  project_id: string;
  user_id: string | null;
  admin_owner_id: string | null;
  status: "open" | "pending" | "resolved" | "closed";
  priority: "P0" | "P1" | "P2";
  category: string;
  body: string;
  created_at: string;
  updated_at: string;
};

export type InternalNote = {
  note_id: string;
  project_id: string;
  admin_user_id: string;
  note_type: string;
  body: string;
  created_at: string;
};

export type ManualIntervention = {
  manual_intervention_id: string;
  project_id: string;
  admin_user_id: string;
  category: string;
  minutes: number;
  body: string | null;
  created_at: string;
};

export type AiCost = {
  ai_cost_id: string;
  project_id: string;
  admin_user_id: string;
  task_type: string;
  provider: string;
  cost_cents: number;
  generation_run_id: string | null;
  created_at: string;
};

export type AdminProjectDetail = ProjectSummary & {
  audio_chunks: AudioChunkRecord[];
  transcript_segments: TranscriptSegment[];
  internal_notes: InternalNote[];
  manual_interventions: ManualIntervention[];
  ai_costs: AiCost[];
};

export type HouseholdOpsRow = {
  project_id: string;
  status: ProjectStatus;
  payment_status: "not_required" | "pending" | "paid" | "waived";
  ai_cost_cents: number;
  manual_intervention_count: number;
  manual_minutes: number;
  ops_owner_id: string | null;
  stuck_reason: string | null;
  stuck_at: string | null;
};

export type HouseholdOpsExport = {
  households: HouseholdOpsRow[];
};

export type AlertRecord = {
  alert_id: string;
  path: string;
  method: string;
  error_type: string;
  message: string;
  created_at: string;
};

export type RetryTaskResult = {
  task_id: string;
  status: "queued";
};

export type DeletionRequest = {
  deletion_request_id: string;
  project_id: string;
  requested_at: string;
  execute_after_at: string;
  executed_at: string | null;
  status: "pending" | "executed" | "cancelled";
};

export type PilotMetrics = {
  households_total: number;
  completion_rate: number;
  effective_interview_completion_rate: number;
  family_correction_completion_rate: number;
  major_fact_error_complaint_rate: number;
  recommend_rate: number;
  nps: number | null;
  manual_minutes_per_household: number | null;
  deposit_rate: number;
  feedback_count: number;
};
