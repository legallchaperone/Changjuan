from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from changjuan_core.ai.contracts import ClaimDraft, CorrectionAction
from changjuan_core.compliance.audit import AuditLog
from changjuan_core.compliance.encryption import KMSPIIKeyProvider
from changjuan_core.story.pdf import render_story_pdf
from fastapi import Depends, FastAPI, Header, HTTPException, Request, WebSocket
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import ValidationError
from starlette.websockets import WebSocketDisconnect

from .auth import (
    current_admin_id,
    current_user_id,
    decode_token,
    ensure_token_active,
    ensure_token_type,
    get_store,
    issue_token,
    new_token_session_id,
    require_admin_roles,
)
from .contracts import (
    AdminNoteCreate,
    AiCostCreate,
    ApiResponse,
    AudioChunkPresignRequest,
    AudioChunkUpload,
    ConsentCreate,
    CorrectionCreate,
    FeedbackCreate,
    InterviewEndRequest,
    ManualInterventionCreate,
    ManualPaymentMark,
    PhotoAnalysisCreate,
    PhotoCompleteRequest,
    PhotoPresignRequest,
    ProjectCreate,
    ProjectPatch,
    SensitiveClaimReview,
    StoryCommentCreate,
    StoryShareLinkCreate,
    StuckProjectAssign,
    SupportTicketCreate,
    SupportTicketPatch,
    VerificationIssueResolve,
    WxLoginRequest,
)
from .observability import configure_observability, report_exception
from .settings import settings
from .sqlalchemy_store import SqlAlchemyStore
from .storage import ObjectStorageConfig
from .store import ConsentRecord, DeletionRequestRecord, InMemoryStore
from .wechat import WechatLoginError, resolve_wechat_identity

OPS_ADMIN_ROLES = ("super_admin", "ops")
REVIEW_ADMIN_ROLES = ("super_admin", "ops", "reviewer")


def _create_store() -> InMemoryStore:
    if settings.store_backend == "memory":
        return InMemoryStore(whitelist_openids=settings.pilot_whitelist_openids)
    if settings.store_backend == "sqlalchemy":
        return SqlAlchemyStore(
            settings.database_url,
            whitelist_openids=settings.pilot_whitelist_openids,
            create_schema=settings.sqlalchemy_create_schema,
            hydrate=True,
            audio_kms_key_id=settings.aliyun_oss_kms_key_id,
        )
    raise RuntimeError(f"unsupported STORE_BACKEND={settings.store_backend}")


def create_app() -> FastAPI:
    app = FastAPI(title="Changjuan Phase 1 API", version="0.1.0")
    observability = configure_observability(app, settings)
    object_storage = ObjectStorageConfig.from_settings(settings)
    store = _create_store()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def _store() -> InMemoryStore:
        return store

    app.dependency_overrides[get_store] = _store

    @app.middleware("http")
    async def rate_limit(request: Request, call_next):
        forwarded_for = request.headers.get("x-forwarded-for")
        client_host = forwarded_for.split(",", 1)[0].strip() if forwarded_for else (request.client.host if request.client else "unknown")
        key = f"{client_host}:{request.url.path}"
        limit = 240 if request.url.path.endswith("/audio-chunks") else 60
        if not store.accept_rate_limited_request(key, limit=limit):
            return Response(
                content=ApiResponse(code=42901, data={}, message="rate limit exceeded").model_dump_json(),
                media_type="application/json",
                status_code=429,
            )
        try:
            return await call_next(request)
        except Exception as exc:
            store.record_alert(request.url.path, request.method, exc)
            report_exception(app, exc, path=request.url.path, method=request.method)
            return Response(
                content=ApiResponse(code=50001, data={}, message="internal server error").model_dump_json(),
                media_type="application/json",
                status_code=500,
            )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_, exc: HTTPException):
        detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
        code = detail.get("code", _default_code(exc.status_code))
        return Response(
            content=ApiResponse(code=code, data={}, message=detail.get("message", "error")).model_dump_json(),
            media_type="application/json",
            status_code=exc.status_code,
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_exception_handler(_, exc: RequestValidationError):
        return Response(
            content=ApiResponse(
                code=42201,
                data={"errors": _validation_errors(exc)},
                message="validation error",
            ).model_dump_json(),
            media_type="application/json",
            status_code=422,
        )

    @app.get("/healthz")
    def healthz() -> ApiResponse:
        production_errors = settings.production_readiness_errors()
        return ApiResponse(
            data={
                "status": "degraded" if production_errors else "ok",
                "production_readiness": {
                    "ready": not production_errors,
                    "errors": production_errors,
                },
                "observability": observability.health_payload(),
                "runtime_dependencies": {
                    "database": _configured_status(settings.database_url),
                    "redis": _configured_status(settings.redis_url),
                    "object_storage": object_storage.readiness_payload(),
                },
            }
        )

    @app.post("/api/v1/auth/wx-login")
    def wx_login(payload: WxLoginRequest, db: InMemoryStore = Depends(get_store)) -> ApiResponse:
        try:
            wechat_identity = resolve_wechat_identity(payload, settings)
        except WechatLoginError as exc:
            raise HTTPException(status_code=422, detail={"code": 42201, "message": str(exc)}) from exc
        if not db.is_pilot_whitelisted(wechat_identity.openid):
            raise HTTPException(status_code=403, detail={"code": 40301, "message": "内测名额暂未开放"})
        pii_encryptor = KMSPIIKeyProvider(settings.pii_kms_key_id).encryptor() if payload.phone_e164 else None
        user = db.upsert_user(
            wechat_identity.openid,
            payload.nickname,
            payload.wx_unionid or wechat_identity.unionid,
            payload.avatar_url,
            payload.phone_e164,
            pii_encryptor,
        )
        token_session_id = new_token_session_id()
        return ApiResponse(
            data={
                "access_token": issue_token(user.id, "user", session_id=token_session_id),
                "refresh_token": issue_token(user.id, "user", token_type="refresh", session_id=token_session_id),
                "user_id": str(user.id),
            }
        )

    @app.post("/api/v1/auth/refresh")
    def refresh(claims: dict = Depends(decode_token), db: InMemoryStore = Depends(get_store)) -> ApiResponse:
        ensure_token_active(claims, db)
        ensure_token_type(claims, "refresh")
        if claims.get("role") != "user":
            raise HTTPException(status_code=403, detail={"code": 40301, "message": "forbidden"})
        user_id = UUID(str(claims["sub"]))
        return ApiResponse(
            data={
                "access_token": issue_token(user_id, "user", session_id=str(claims["sid"])),
                "refresh_token": claims["_raw_token"],
            }
        )

    @app.post("/api/v1/auth/logout")
    def logout(claims: dict = Depends(decode_token), db: InMemoryStore = Depends(get_store)) -> ApiResponse:
        ensure_token_active(claims, db)
        db.revoke_token_id(str(claims.get("jti")))
        db.revoke_token_session(str(claims.get("sid")))
        return ApiResponse(data={"revoked": True})

    @app.post("/api/v1/projects")
    def create_project(
        payload: ProjectCreate,
        user_id: UUID = Depends(current_user_id),
        db: InMemoryStore = Depends(get_store),
    ) -> ApiResponse:
        project = db.create_project(user_id, payload.model_dump())
        return ApiResponse(
            data={
                "project_id": str(project.id),
                "status": project.status,
                "payment_required": True,
                "payment_mode": "manual",
                "payment_instruction": settings.manual_payment_instruction,
                "next_action": "complete_manual_deposit",
            }
        )

    @app.get("/api/v1/projects")
    def list_projects(user_id: UUID = Depends(current_user_id), db: InMemoryStore = Depends(get_store)) -> ApiResponse:
        projects = [project for project in db.projects.values() if project.user_id == user_id and not project.deleted_at]
        return ApiResponse(data={"projects": [_project_payload(project) for project in projects]})

    @app.get("/api/v1/projects/{project_id}")
    def get_project(project_id: UUID, user_id: UUID = Depends(current_user_id), db: InMemoryStore = Depends(get_store)) -> ApiResponse:
        project = _owned_project(db, project_id, user_id)
        return ApiResponse(data=_project_payload(project))

    @app.patch("/api/v1/projects/{project_id}")
    def patch_project(
        project_id: UUID,
        payload: ProjectPatch,
        user_id: UUID = Depends(current_user_id),
        db: InMemoryStore = Depends(get_store),
    ) -> ApiResponse:
        project = _owned_project(db, project_id, user_id)
        changed = False
        if payload.title:
            project.title = payload.title
            changed = True
        if payload.themes is not None:
            project.themes = payload.themes
            changed = True
        if changed:
            db.touch_project(project.id)
        return ApiResponse(data=_project_payload(project))

    @app.delete("/api/v1/projects/{project_id}")
    def delete_project(project_id: UUID, user_id: UUID = Depends(current_user_id), db: InMemoryStore = Depends(get_store)) -> ApiResponse:
        project = _owned_project(db, project_id, user_id)
        deletion = db.request_deletion(project.id, requested_by_user_id=user_id)
        db.audit.record(
            AuditLog(
                actor_id=user_id,
                action="deletion.request",
                resource_type="project",
                resource_id=project_id,
            )
        )
        return ApiResponse(data=_deletion_request_payload(deletion))

    @app.get("/api/v1/projects/{project_id}/deletion-request")
    def deletion_request_status(project_id: UUID, user_id: UUID = Depends(current_user_id), db: InMemoryStore = Depends(get_store)) -> ApiResponse:
        project = db.projects.get(project_id)
        if not project or project.user_id != user_id or not project.deletion_request_id:
            raise HTTPException(status_code=404, detail={"code": 40401, "message": "not found"})
        return ApiResponse(data=_deletion_request_payload(db.deletion_requests[project.deletion_request_id]))

    @app.get("/api/v1/projects/{project_id}/export")
    def export_project(project_id: UUID, user_id: UUID = Depends(current_user_id), db: InMemoryStore = Depends(get_store)) -> ApiResponse:
        project = _owned_project(db, project_id, user_id)
        db.audit.record(
            AuditLog(
                actor_id=user_id,
                action="project.export",
                resource_type="project",
                resource_id=project_id,
            )
        )
        return ApiResponse(data=_project_export_payload(project, db))

    @app.post("/api/v1/projects/{project_id}/feedback")
    def create_feedback(project_id: UUID, payload: FeedbackCreate, user_id: UUID = Depends(current_user_id), db: InMemoryStore = Depends(get_store)) -> ApiResponse:
        _owned_project(db, project_id, user_id)
        feedback = db.create_feedback(project_id, user_id, payload.model_dump())
        db.audit.record(
            AuditLog(
                actor_id=user_id,
                action="feedback.create",
                resource_type="project",
                resource_id=project_id,
                metadata=payload.model_dump(mode="json", exclude_none=True),
            )
        )
        return ApiResponse(data=_feedback_payload(feedback))

    @app.post("/api/v1/projects/{project_id}/support-tickets")
    def create_support_ticket(
        project_id: UUID,
        payload: SupportTicketCreate,
        user_id: UUID = Depends(current_user_id),
        db: InMemoryStore = Depends(get_store),
    ) -> ApiResponse:
        _owned_project(db, project_id, user_id)
        ticket = db.create_support_ticket(project_id, user_id, payload.model_dump())
        db.audit.record(
            AuditLog(
                actor_id=user_id,
                action="support_ticket.create",
                resource_type="support_ticket",
                resource_id=ticket.id,
                metadata=payload.model_dump(mode="json"),
            )
        )
        return ApiResponse(data=_support_ticket_payload(ticket))

    @app.post("/api/v1/projects/{project_id}/photos/presign")
    def presign_photo(project_id: UUID, payload: PhotoPresignRequest, user_id: UUID = Depends(current_user_id), db: InMemoryStore = Depends(get_store)) -> ApiResponse:
        _owned_project(db, project_id, user_id)
        photo_id = uuid4()
        oss_key = f"photos/{project_id}/{photo_id}-{payload.filename}"
        return ApiResponse(
            data={
                "upload_url": object_storage.upload_url(oss_key),
                "oss_key": oss_key,
                "headers": object_storage.upload_headers(payload.content_type),
            }
        )

    @app.post("/api/v1/projects/{project_id}/photos/complete")
    def complete_photo(project_id: UUID, payload: PhotoCompleteRequest, user_id: UUID = Depends(current_user_id), db: InMemoryStore = Depends(get_store)) -> ApiResponse:
        _owned_project(db, project_id, user_id)
        from .store import PhotoRecord

        if not payload.oss_key.startswith(f"photos/{project_id}/"):
            raise HTTPException(status_code=422, detail={"code": 42201, "message": "photo oss_key must be under the project photo prefix"})
        photo_count = sum(1 for photo in db.photos.values() if photo.project_id == project_id and not photo.deleted_at)
        if photo_count >= 10:
            raise HTTPException(status_code=409, detail={"code": 40901, "message": "maximum 10 photos per project"})
        photo_id = uuid4()
        photo = PhotoRecord(
            id=photo_id,
            project_id=project_id,
            oss_key=payload.oss_key,
            thumbnail_oss_key=f"photos/{project_id}/thumbnails/{photo_id}.jpg",
            caption=payload.caption,
        )
        db.record_photo(photo)
        return ApiResponse(
            data={
                "photo_id": str(photo.id),
                "thumbnail_oss_key": photo.thumbnail_oss_key,
                "photo_count": photo_count + 1,
                "internal_photo_hypothesis_only": True,
            }
        )

    @app.get("/api/v1/projects/{project_id}/photos")
    def list_photos(project_id: UUID, user_id: UUID = Depends(current_user_id), db: InMemoryStore = Depends(get_store)) -> ApiResponse:
        _owned_project(db, project_id, user_id)
        return ApiResponse(
            data={
                "photos": [
                    _photo_payload(photo)
                    for photo in db.photos.values()
                    if photo.project_id == project_id and not photo.deleted_at
                ]
            }
        )

    @app.delete("/api/v1/photos/{photo_id}")
    def delete_photo(photo_id: UUID, user_id: UUID = Depends(current_user_id), db: InMemoryStore = Depends(get_store)) -> ApiResponse:
        photo = db.photos.get(photo_id)
        if not photo:
            raise HTTPException(status_code=404, detail={"code": 40401, "message": "not found"})
        _owned_project(db, photo.project_id, user_id)
        from datetime import timedelta

        photo.deleted_at = datetime.now(UTC)
        photo.purge_after_at = photo.deleted_at + timedelta(days=7)
        db.save_photo(photo)
        db.touch_project(photo.project_id, photo.deleted_at)
        return ApiResponse(data={"deleted": True})

    @app.post("/api/v1/projects/{project_id}/interview-sessions")
    def create_interview_session(project_id: UUID, user_id: UUID = Depends(current_user_id), db: InMemoryStore = Depends(get_store)) -> ApiResponse:
        project = _owned_project(db, project_id, user_id)
        if project.payment_status not in {"paid", "waived"}:
            raise HTTPException(status_code=409, detail={"code": 40901, "message": "manual payment required before interview"})
        if not project.has_interview_consent:
            raise HTTPException(
                status_code=422,
                detail={"code": 42201, "message": "interview consent required before interview"},
            )
        photo_count = sum(1 for photo in db.photos.values() if photo.project_id == project_id and not photo.deleted_at)
        if photo_count < 3:
            raise HTTPException(
                status_code=422,
                detail={"code": 42201, "message": "at least 3 photos required before interview"},
            )
        session = db.create_session(project_id)
        return ApiResponse(data={"session_id": str(session.id), "status": session.status})

    @app.get("/api/v1/interview-sessions/{session_id}")
    def get_session(session_id: UUID, user_id: UUID = Depends(current_user_id), db: InMemoryStore = Depends(get_store)) -> ApiResponse:
        session = db.sessions.get(session_id)
        if not session:
            raise HTTPException(status_code=404, detail={"code": 40401, "message": "not found"})
        _owned_project(db, session.project_id, user_id)
        return ApiResponse(data={"session_id": str(session.id), "status": session.status})

    @app.post("/api/v1/interview-sessions/{session_id}/start")
    def start_session(session_id: UUID, user_id: UUID = Depends(current_user_id), db: InMemoryStore = Depends(get_store)) -> ApiResponse:
        session = _owned_session(db, session_id, user_id)
        if session.status != "scheduled":
            raise HTTPException(status_code=409, detail={"code": 40901, "message": "session must be scheduled before start"})
        session.status = "in_progress"
        session.started_at = datetime.now(UTC)
        project = db.projects[session.project_id]
        project.status = "interview_in_progress"
        db.save_session(session)
        db.touch_project(project.id)
        return ApiResponse(data={"session_id": str(session.id), "status": session.status})

    @app.post("/api/v1/interview-sessions/{session_id}/end")
    def end_session(
        session_id: UUID,
        payload: InterviewEndRequest | None = None,
        user_id: UUID = Depends(current_user_id),
        db: InMemoryStore = Depends(get_store),
    ) -> ApiResponse:
        session = _owned_session(db, session_id, user_id)
        if session.status != "in_progress":
            raise HTTPException(status_code=409, detail={"code": 40901, "message": "session must be in_progress before end"})
        target_status = payload.status if payload else "completed"
        if target_status not in {
            "completed",
            "aborted_by_storyteller",
            "aborted_technical",
            "completed_short",
        }:
            raise HTTPException(
                status_code=422,
                detail={"code": 42201, "message": "invalid session end status"},
            )
        session.status = target_status
        session.ended_at = datetime.now(UTC)
        project = db.projects[session.project_id]
        project.status = "interview_completed"
        db.save_session(session)
        db.touch_project(project.id)
        return ApiResponse(data={"session_id": str(session.id), "status": session.status})

    @app.post("/api/v1/interview-sessions/{session_id}/audio-chunks/presign")
    def presign_audio_chunk(
        session_id: UUID,
        payload: AudioChunkPresignRequest,
        user_id: UUID = Depends(current_user_id),
        db: InMemoryStore = Depends(get_store),
    ) -> ApiResponse:
        session = _owned_session(db, session_id, user_id)
        if session.status != "in_progress":
            raise HTTPException(status_code=409, detail={"code": 40901, "message": "session must be in_progress"})
        if not payload.content_type.startswith("audio/"):
            raise HTTPException(status_code=422, detail={"code": 42201, "message": "audio content_type required"})
        extension = _audio_extension(payload.content_type)
        oss_key = f"audio/{session.project_id}/interview-{session.id}-{payload.sequence_number}.{extension}"
        return ApiResponse(
            data={
                "upload_url": object_storage.upload_url(oss_key),
                "oss_key": oss_key,
                "headers": object_storage.upload_headers(payload.content_type),
            }
        )

    @app.post("/api/v1/interview-sessions/{session_id}/audio-chunks")
    def upload_audio_chunk(
        session_id: UUID,
        payload: AudioChunkUpload,
        user_id: UUID = Depends(current_user_id),
        db: InMemoryStore = Depends(get_store),
    ) -> ApiResponse:
        session = _owned_session(db, session_id, user_id)
        if session.status != "in_progress":
            raise HTTPException(status_code=409, detail={"code": 40901, "message": "session must be in_progress"})
        try:
            response = _record_audio_chunk_payload(db, session, payload)
        except ValueError as exc:
            status_code = 429 if "rate limit" in str(exc) else 422
            raise HTTPException(status_code=status_code, detail={"code": _default_code(status_code), "message": str(exc)}) from exc
        return ApiResponse(data=response)

    @app.get("/api/v1/interview-sessions/{session_id}/recovery")
    def session_recovery(session_id: UUID, user_id: UUID = Depends(current_user_id), db: InMemoryStore = Depends(get_store)) -> ApiResponse:
        _owned_session(db, session_id, user_id)
        return ApiResponse(data=db.session_recovery(session_id))

    @app.websocket("/api/v1/interview-sessions/{session_id}/stream")
    async def stream_session(websocket: WebSocket, session_id: UUID):
        try:
            user_id = _websocket_user_id(websocket, store)
            session = _owned_session(store, session_id, user_id)
            if session.status != "in_progress":
                raise HTTPException(status_code=409, detail={"code": 40901, "message": "session must be in_progress"})
        except HTTPException:
            await websocket.close(code=1008)
            return

        await websocket.accept()
        await websocket.send_json({"session_id": str(session_id), "chunk_duration_ms": "300-500", "max_chunks_per_minute": 240})
        while True:
            try:
                message = await websocket.receive_json()
            except WebSocketDisconnect:
                return
            try:
                payload = AudioChunkUpload.model_validate(message)
                response = _record_audio_chunk_payload(store, session, payload)
            except ValidationError as exc:
                await websocket.send_json({"accepted": False, "code": 42201, "message": str(exc)})
                continue
            except ValueError as exc:
                status_code = 429 if "rate limit" in str(exc) else 422
                await websocket.send_json({"accepted": False, "code": _default_code(status_code), "message": str(exc)})
                continue
            await websocket.send_json(response)

    @app.post("/api/v1/projects/{project_id}/consents")
    def create_consent(project_id: UUID, payload: ConsentCreate, user_id: UUID = Depends(current_user_id), db: InMemoryStore = Depends(get_store)) -> ApiResponse:
        _owned_project(db, project_id, user_id)
        if payload.consent_type not in {"interview_consent", "family_sharing"}:
            raise HTTPException(status_code=422, detail={"code": 42201, "message": "unsupported consent_type"})
        if payload.method not in {"text", "audio"}:
            raise HTTPException(status_code=422, detail={"code": 42201, "message": "unsupported consent method"})
        if payload.method == "audio" and not payload.evidence_oss_key:
            raise HTTPException(status_code=422, detail={"code": 42201, "message": "audio consent evidence required"})
        if payload.evidence_oss_key and not payload.evidence_oss_key.startswith(f"consents/{project_id}/"):
            raise HTTPException(status_code=422, detail={"code": 42201, "message": "consent evidence oss_key must be under the project consent prefix"})
        consent = ConsentRecord(
            id=uuid4(),
            project_id=project_id,
            user_id=user_id,
            consent_type=payload.consent_type,
            method=payload.method,
            evidence_oss_key=payload.evidence_oss_key,
        )
        db.record_consent(consent)
        db.audit.record(
            AuditLog(
                actor_id=user_id,
                action="consent.create",
                resource_type="consent",
                resource_id=consent.id,
                metadata=payload.model_dump(mode="json", exclude_none=True),
            )
        )
        return ApiResponse(data=_consent_payload(consent))

    @app.post("/api/v1/projects/{project_id}/consents/{consent_id}/withdraw")
    def withdraw_consent(
        project_id: UUID,
        consent_id: UUID,
        user_id: UUID = Depends(current_user_id),
        db: InMemoryStore = Depends(get_store),
    ) -> ApiResponse:
        _owned_project(db, project_id, user_id)
        consent = db.consent_records.get(consent_id)
        if not consent or consent.user_id != user_id:
            raise HTTPException(status_code=404, detail={"code": 40401, "message": "not found"})
        withdrawn = db.withdraw_consent(project_id, consent_id)
        if not withdrawn:
            raise HTTPException(status_code=404, detail={"code": 40401, "message": "not found"})
        db.audit.record(
            AuditLog(
                actor_id=user_id,
                action="consent.withdraw",
                resource_type="consent",
                resource_id=consent_id,
                metadata={"consent_type": withdrawn.consent_type},
            )
        )
        return ApiResponse(data=_consent_payload(withdrawn))

    @app.get("/api/v1/projects/{project_id}/corrections/pending")
    def pending_corrections(project_id: UUID, user_id: UUID = Depends(current_user_id), db: InMemoryStore = Depends(get_store)) -> ApiResponse:
        _owned_project(db, project_id, user_id)
        claims = sorted(
            (
                claim
                for claim in db.seed_claims_for_project(project_id)
                if not claim.deleted_at and claim.verification_status == "pending"
            ),
            key=lambda claim: claim.claim_priority,
        )
        return ApiResponse(data={"claims": [claim.model_dump(mode="json") for claim in claims[:20]]})

    @app.get("/api/v1/claims/{claim_id}")
    def get_claim(claim_id: UUID, user_id: UUID = Depends(current_user_id), db: InMemoryStore = Depends(get_store)) -> ApiResponse:
        claim = _owned_claim(db, claim_id, user_id)
        return ApiResponse(data=claim.model_dump(mode="json"))

    @app.get("/api/v1/claims/{claim_id}/corrections")
    def claim_corrections(claim_id: UUID, user_id: UUID = Depends(current_user_id), db: InMemoryStore = Depends(get_store)) -> ApiResponse:
        project_id = _claim_project_id(db, claim_id)
        if not project_id:
            raise HTTPException(status_code=404, detail={"code": 40401, "message": "not found"})
        _owned_project(db, project_id, user_id)
        corrections = [
            correction
            for correction in sorted(db.claim_corrections.values(), key=lambda item: item.created_at)
            if correction.claim_id == claim_id
        ]
        return ApiResponse(data={"corrections": [_claim_correction_payload(correction) for correction in corrections]})

    @app.post("/api/v1/claims/{claim_id}/corrections")
    def correct_claim(claim_id: UUID, payload: CorrectionCreate, user_id: UUID = Depends(current_user_id), db: InMemoryStore = Depends(get_store)) -> ApiResponse:
        claim = _owned_claim(db, claim_id, user_id)
        action = CorrectionAction(payload.action)
        status_map = {
            CorrectionAction.CONFIRM: "confirmed",
            CorrectionAction.MODIFY: "modified",
            CorrectionAction.UNSURE: "marked_unsure",
            CorrectionAction.HIDE_FROM_FAMILY: "hidden",
            CorrectionAction.DELETE: "deleted",
        }
        claim.verification_status = status_map[action]
        if action == CorrectionAction.MODIFY:
            claim.modified_text = payload.modified_text
        if action == CorrectionAction.DELETE:
            from datetime import UTC, datetime, timedelta

            claim.deleted_at = datetime.now(UTC)
            claim.purge_after_at = claim.deleted_at + timedelta(days=7)
        project_id = _claim_project_id(db, claim_id)
        if project_id:
            db.save_claim(project_id, claim)
            db.touch_project(project_id)
        db.record_claim_correction(claim_id, user_id, payload.model_dump(mode="json", exclude_none=True))
        db.audit.record(
            AuditLog(
                actor_id=user_id,
                action="claim.correction",
                resource_type="claim",
                resource_id=claim_id,
                metadata=payload.model_dump(mode="json", exclude_none=True),
            )
        )
        return ApiResponse(data=claim.model_dump(mode="json"))

    @app.post("/api/v1/projects/{project_id}/corrections/complete")
    def complete_corrections(project_id: UUID, user_id: UUID = Depends(current_user_id), db: InMemoryStore = Depends(get_store)) -> ApiResponse:
        _owned_project(db, project_id, user_id)
        try:
            db.complete_corrections(project_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail={"code": 42201, "message": str(exc)}) from exc
        db.audit.record(
            AuditLog(
                actor_id=user_id,
                action="corrections.complete",
                resource_type="project",
                resource_id=project_id,
            )
        )
        return ApiResponse(data={"status": "family_correction_completed"})

    @app.post("/api/v1/projects/{project_id}/drafts/generate")
    def generate_drafts(project_id: UUID, user_id: UUID = Depends(current_user_id), db: InMemoryStore = Depends(get_store)) -> ApiResponse:
        _owned_project(db, project_id, user_id)
        try:
            page = db.generate_story(project_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail={"code": 42201, "message": str(exc)}) from exc
        return ApiResponse(data={"story_page_id": str(page.id), "chapters": [chapter.model_dump(mode="json") for chapter in page.draft.chapters]})

    @app.get("/api/v1/projects/{project_id}/drafts")
    def get_drafts(project_id: UUID, user_id: UUID = Depends(current_user_id), db: InMemoryStore = Depends(get_store)) -> ApiResponse:
        project = _owned_project(db, project_id, user_id)
        page = db.story_pages.get(project.story_page_id) if project.story_page_id else None
        return ApiResponse(data={"chapters": [chapter.model_dump(mode="json") for chapter in page.draft.chapters] if page and page.draft else []})

    @app.post("/api/v1/projects/{project_id}/verify")
    def verify_project(project_id: UUID, user_id: UUID = Depends(current_user_id), db: InMemoryStore = Depends(get_store)) -> ApiResponse:
        _owned_project(db, project_id, user_id)
        return ApiResponse(data={"issues": db.verify_project(project_id)})

    @app.post("/api/v1/projects/{project_id}/request-second-consent")
    def request_second_consent(project_id: UUID, user_id: UUID = Depends(current_user_id), db: InMemoryStore = Depends(get_store)) -> ApiResponse:
        _owned_project(db, project_id, user_id)
        try:
            db.request_second_consent(project_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail={"code": 42201, "message": str(exc)}) from exc
        return ApiResponse(data={"status": "elder_second_consent_pending"})

    @app.post("/api/v1/projects/{project_id}/publish")
    def publish(project_id: UUID, user_id: UUID = Depends(current_user_id), db: InMemoryStore = Depends(get_store)) -> ApiResponse:
        project = _owned_project(db, project_id, user_id)
        allowed, reasons = db.publish(project_id)
        db.audit.record(
            AuditLog(
                actor_id=user_id,
                action="story.publish_decision",
                resource_type="project",
                resource_id=project_id,
                metadata={
                    "allowed": allowed,
                    "reasons": "; ".join(reasons),
                    "story_page_id": str(project.story_page_id) if project.story_page_id else "",
                },
            )
        )
        if not allowed:
            raise HTTPException(status_code=422, detail={"code": 42201, "message": "; ".join(reasons)})
        return ApiResponse(data={"status": "published"})

    @app.get("/api/v1/story-pages/{story_page_id}")
    def story_page(
        story_page_id: UUID,
        share_token: str | None = None,
        password: str | None = None,
        db: InMemoryStore = Depends(get_store),
    ) -> ApiResponse:
        page = db.story_pages.get(story_page_id)
        if not page or not page.enabled or page.deleted_at:
            raise HTTPException(status_code=404, detail={"code": 40401, "message": "not found"})
        link = _active_story_link(db, page, share_token, password)
        _, media_access_token = db.record_story_access(page.id, link.id)
        return ApiResponse(data=_story_page_payload(page, db, media_access_token))

    @app.post("/api/v1/story-pages/{story_page_id}/share-links")
    def create_share_link(
        story_page_id: UUID,
        payload: StoryShareLinkCreate | None = None,
        user_id: UUID = Depends(current_user_id),
        db: InMemoryStore = Depends(get_store),
    ) -> ApiResponse:
        page = db.story_pages.get(story_page_id)
        if not page or page.deleted_at:
            raise HTTPException(status_code=404, detail={"code": 40401, "message": "not found"})
        _owned_project(db, page.project_id, user_id)
        payload = payload or StoryShareLinkCreate()
        link, token = db.create_share_link(page.id, user_id, password=payload.password)
        return ApiResponse(data=_share_link_payload(link, token))

    @app.delete("/api/v1/story-pages/{story_page_id}/share-links/{share_link_id}")
    def revoke_share_link(
        story_page_id: UUID,
        share_link_id: UUID,
        user_id: UUID = Depends(current_user_id),
        db: InMemoryStore = Depends(get_store),
    ) -> ApiResponse:
        page = _owned_story_page_for_link(db, story_page_id, share_link_id, user_id)
        link = db.revoke_share_link(share_link_id)
        db.audit.record(
            AuditLog(
                actor_id=user_id,
                action="story.share_link.revoke",
                resource_type="story_page",
                resource_id=page.id,
                metadata={"share_link_id": str(share_link_id)},
            )
        )
        return ApiResponse(data=_share_link_payload(link))

    @app.post("/api/v1/story-pages/{story_page_id}/share-links/{share_link_id}/reset")
    def reset_share_link(
        story_page_id: UUID,
        share_link_id: UUID,
        user_id: UUID = Depends(current_user_id),
        db: InMemoryStore = Depends(get_store),
    ) -> ApiResponse:
        page = _owned_story_page_for_link(db, story_page_id, share_link_id, user_id)
        link, token = db.reset_share_link(share_link_id)
        db.audit.record(
            AuditLog(
                actor_id=user_id,
                action="story.share_link.reset",
                resource_type="story_page",
                resource_id=page.id,
                metadata={"share_link_id": str(share_link_id)},
            )
        )
        return ApiResponse(data=_share_link_payload(link, token))

    @app.post("/api/v1/story-pages/{story_page_id}/comments")
    def create_story_comment(
        story_page_id: UUID,
        payload: StoryCommentCreate,
        db: InMemoryStore = Depends(get_store),
    ) -> ApiResponse:
        page = db.story_pages.get(story_page_id)
        if not page or not page.enabled or page.deleted_at:
            raise HTTPException(status_code=404, detail={"code": 40401, "message": "not found"})
        link = _active_story_link(db, page, payload.share_token, payload.password)
        comment = db.create_family_comment(page.id, link.id, payload.display_name, payload.body)
        return ApiResponse(data=_comment_payload(comment))

    @app.get("/api/v1/story-pages/{story_page_id}/audio/{segment_id}")
    def story_audio(
        story_page_id: UUID,
        segment_id: UUID,
        access_token: str | None = None,
        db: InMemoryStore = Depends(get_store),
    ) -> Response:
        page = db.story_pages.get(story_page_id)
        if not page or not page.enabled or page.deleted_at:
            raise HTTPException(status_code=404, detail={"code": 40401, "message": "not found"})
        if not db.has_media_access(page.id, access_token):
            raise HTTPException(status_code=403, detail={"code": 40301, "message": "valid story access required"})
        if not _story_has_segment(page, db, segment_id):
            raise HTTPException(status_code=404, detail={"code": 40401, "message": "not found"})
        return Response(content=b"phase1-audio-snippet", media_type="audio/mpeg")

    @app.post("/api/v1/story-pages/{story_page_id}/pdf-export")
    def pdf_export(
        story_page_id: UUID,
        share_token: str | None = None,
        password: str | None = None,
        authorization: str | None = Header(default=None),
        db: InMemoryStore = Depends(get_store),
    ) -> Response:
        page = db.story_pages.get(story_page_id)
        if not page or not page.draft or page.deleted_at:
            raise HTTPException(status_code=404, detail={"code": 40401, "message": "not found"})
        if authorization:
            claims = decode_token(authorization)
            ensure_token_active(claims, db)
            ensure_token_type(claims, "access")
            if claims.get("role") != "user":
                raise HTTPException(status_code=403, detail={"code": 40301, "message": "forbidden"})
            project = _owned_project(db, page.project_id, UUID(str(claims["sub"])))
        else:
            if not page.enabled:
                raise HTTPException(status_code=404, detail={"code": 40401, "message": "not found"})
            _active_story_link(db, page, share_token, password)
            project = _admin_project(db, page.project_id)
        pdf = render_story_pdf(page.draft, project.title)
        db.record_pdf_export(project.id, page.id)
        return Response(content=pdf, media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=changjuan-story.pdf"})

    @app.post("/api/v1/admin/auth/login")
    def admin_login(payload: dict, db: InMemoryStore = Depends(get_store)) -> ApiResponse:
        admin_user = db.authenticate_admin(payload.get("email"), payload.get("password"))
        if not admin_user:
            raise HTTPException(status_code=401, detail={"code": 40101, "message": "unauthenticated"})
        access_token = issue_token(admin_user.id, admin_user.role)
        db.record_admin_login(admin_user.id, access_token)
        return ApiResponse(data={"access_token": access_token, "admin_user_id": str(admin_user.id)})

    @app.get("/api/v1/admin/projects")
    def admin_projects(_: UUID = Depends(current_admin_id), db: InMemoryStore = Depends(get_store)) -> ApiResponse:
        return ApiResponse(data={"projects": [_project_payload(project) for project in db.projects.values()]})

    @app.get("/api/v1/admin/projects/{project_id}")
    def admin_project(project_id: UUID, _: UUID = Depends(current_admin_id), db: InMemoryStore = Depends(get_store)) -> ApiResponse:
        return ApiResponse(data=_admin_project_payload(_admin_project(db, project_id), db))

    @app.post("/api/v1/admin/projects/{project_id}/notes")
    def admin_note(
        project_id: UUID,
        payload: AdminNoteCreate,
        admin_id: UUID = Depends(require_admin_roles(*REVIEW_ADMIN_ROLES)),
        db: InMemoryStore = Depends(get_store),
    ) -> ApiResponse:
        _admin_project(db, project_id)
        note = db.create_internal_note(project_id, admin_id, payload.model_dump())
        db.audit.record(AuditLog(actor_id=admin_id, action="admin.note", resource_type="project", resource_id=project_id, metadata=payload.model_dump(mode="json")))
        return ApiResponse(data=_internal_note_payload(note))

    @app.post("/api/v1/admin/projects/{project_id}/mark-payment")
    def mark_payment(
        project_id: UUID,
        payload: ManualPaymentMark,
        admin_id: UUID = Depends(require_admin_roles(*OPS_ADMIN_ROLES)),
        db: InMemoryStore = Depends(get_store),
    ) -> ApiResponse:
        _admin_project(db, project_id)
        if error := payload.phase1_validation_error():
            raise HTTPException(status_code=422, detail={"code": 42201, "message": error})
        project = db.mark_payment(project_id, admin_id, payload.model_dump())
        return ApiResponse(data=_project_payload(project))

    @app.post("/api/v1/admin/projects/{project_id}/manual-interventions")
    def record_manual_intervention(
        project_id: UUID,
        payload: ManualInterventionCreate,
        admin_id: UUID = Depends(require_admin_roles(*OPS_ADMIN_ROLES)),
        db: InMemoryStore = Depends(get_store),
    ) -> ApiResponse:
        _admin_project(db, project_id)
        intervention = db.record_manual_intervention(project_id, admin_id, payload.model_dump())
        db.audit.record(
            AuditLog(
                actor_id=admin_id,
                action="admin.manual_intervention",
                resource_type="project",
                resource_id=project_id,
                metadata=payload.model_dump(mode="json"),
            )
        )
        return ApiResponse(data=_manual_intervention_payload(intervention))

    @app.post("/api/v1/admin/projects/{project_id}/ai-costs")
    def record_ai_cost(
        project_id: UUID,
        payload: AiCostCreate,
        admin_id: UUID = Depends(require_admin_roles(*OPS_ADMIN_ROLES)),
        db: InMemoryStore = Depends(get_store),
    ) -> ApiResponse:
        _admin_project(db, project_id)
        cost = db.record_ai_cost(project_id, admin_id, payload.model_dump())
        db.audit.record(
            AuditLog(
                actor_id=admin_id,
                action="admin.record_ai_cost",
                resource_type="project",
                resource_id=project_id,
                metadata=payload.model_dump(mode="json", exclude_none=True),
            )
        )
        return ApiResponse(data=_ai_cost_payload(cost))

    @app.post("/api/v1/admin/projects/{project_id}/stuck")
    def assign_stuck_project(
        project_id: UUID,
        payload: StuckProjectAssign,
        admin_id: UUID = Depends(require_admin_roles(*OPS_ADMIN_ROLES)),
        db: InMemoryStore = Depends(get_store),
    ) -> ApiResponse:
        project = _admin_project(db, project_id)
        project = db.mark_project_stuck(project.id, payload.owner_id, payload.reason)
        db.audit.record(
            AuditLog(
                actor_id=admin_id,
                action="admin.assign_stuck_project",
                resource_type="project",
                resource_id=project_id,
                metadata={"owner_id": str(payload.owner_id), "reason": payload.reason},
            )
        )
        return ApiResponse(data=_project_payload(project))

    @app.post("/api/v1/admin/photos/{photo_id}/analysis")
    def create_photo_analysis(
        photo_id: UUID,
        payload: PhotoAnalysisCreate,
        admin_id: UUID = Depends(require_admin_roles(*REVIEW_ADMIN_ROLES)),
        db: InMemoryStore = Depends(get_store),
    ) -> ApiResponse:
        photo = db.photos.get(photo_id)
        if not photo or photo.deleted_at:
            raise HTTPException(status_code=404, detail={"code": 40401, "message": "not found"})
        if not _has_photo_uncertainty(payload.hypothesis_text):
            raise HTTPException(status_code=422, detail={"code": 42201, "message": "photo hypothesis requires uncertainty marker"})
        analysis = db.create_photo_analysis(photo_id, payload.hypothesis_text, payload.confidence)
        db.audit.record(
            AuditLog(
                actor_id=admin_id,
                action="admin.photo_analysis.create",
                resource_type="photo_analysis",
                resource_id=analysis.id,
                metadata={"project_id": str(analysis.project_id), "photo_id": str(photo_id)},
            )
        )
        return ApiResponse(data=_photo_analysis_payload(analysis))

    @app.get("/api/v1/admin/projects/{project_id}/photo-analyses")
    def photo_analyses(project_id: UUID, _: UUID = Depends(current_admin_id), db: InMemoryStore = Depends(get_store)) -> ApiResponse:
        _admin_project(db, project_id)
        analyses = [
            _photo_analysis_payload(analysis)
            for analysis in sorted(db.photo_analyses.values(), key=lambda item: item.created_at)
            if analysis.project_id == project_id and not analysis.deleted_at
        ]
        return ApiResponse(data={"photo_analyses": analyses})

    @app.post("/api/v1/admin/photo-analyses/{analysis_id}/correction-candidate")
    def convert_photo_analysis_to_candidate(
        analysis_id: UUID,
        admin_id: UUID = Depends(require_admin_roles(*REVIEW_ADMIN_ROLES)),
        db: InMemoryStore = Depends(get_store),
    ) -> ApiResponse:
        analysis = db.photo_analyses.get(analysis_id)
        if not analysis or analysis.deleted_at:
            raise HTTPException(status_code=404, detail={"code": 40401, "message": "not found"})
        if not analysis.eligible_for_prompt:
            raise HTTPException(status_code=422, detail={"code": 42201, "message": "photo analysis is not eligible for correction candidate"})
        claim = db.convert_photo_analysis_to_candidate(analysis.id)
        db.audit.record(
            AuditLog(
                actor_id=admin_id,
                action="admin.photo_analysis.convert_to_candidate",
                resource_type="photo_analysis",
                resource_id=analysis.id,
                metadata={"claim_id": str(claim.id), "project_id": str(analysis.project_id)},
            )
        )
        return ApiResponse(data={"photo_analysis": _photo_analysis_payload(analysis), "claim": claim.model_dump(mode="json")})

    @app.get("/api/v1/admin/sensitive-claims")
    def sensitive_claims(_: UUID = Depends(current_admin_id), db: InMemoryStore = Depends(get_store)) -> ApiResponse:
        claims = []
        for claim in db.claims.values():
            if claim.deleted_at or claim.human_reviewed or claim.sensitivity_level not in {"sensitive", "highly_sensitive"}:
                continue
            project_id = _claim_project_id(db, claim.id)
            if project_id:
                claims.append(_sensitive_claim_payload(claim, project_id))
        return ApiResponse(data={"claims": sorted(claims, key=lambda item: (item["sensitivity_level"], item["claim_id"]))})

    @app.post("/api/v1/admin/claims/{claim_id}/sensitive-review")
    def review_sensitive_claim(
        claim_id: UUID,
        payload: SensitiveClaimReview,
        admin_id: UUID = Depends(require_admin_roles(*REVIEW_ADMIN_ROLES)),
        db: InMemoryStore = Depends(get_store),
    ) -> ApiResponse:
        claim = db.claims.get(claim_id)
        project_id = _claim_project_id(db, claim_id)
        if not claim or not project_id:
            raise HTTPException(status_code=404, detail={"code": 40401, "message": "not found"})
        if claim.sensitivity_level not in {"sensitive", "highly_sensitive"}:
            raise HTTPException(status_code=422, detail={"code": 42201, "message": "claim is not sensitive"})
        if not payload.resolution_reason.strip():
            raise HTTPException(status_code=422, detail={"code": 42201, "message": "resolution reason required"})
        from datetime import UTC, datetime

        claim.human_reviewed = True
        now = datetime.now(UTC).isoformat()
        for issue in db.verification_issues.values():
            if issue.get("claim_id") == str(claim_id) and issue.get("gate") == "sensitive_content" and not issue.get("resolved_at"):
                issue["resolved_at"] = now
                issue["resolution_reason"] = payload.resolution_reason
                issue["resolved_by_admin_id"] = str(admin_id)
                db.save_verification_issue(UUID(str(issue["id"])), issue)
        db.save_claim(project_id, claim)
        db.mark_verified_if_no_unresolved_blocks(project_id)
        db.audit.record(
            AuditLog(
                actor_id=admin_id,
                action="admin.sensitive_review",
                resource_type="claim",
                resource_id=claim_id,
                reason=payload.resolution_reason,
                metadata={"project_id": str(project_id), "sensitivity_level": claim.sensitivity_level},
            )
        )
        return ApiResponse(data=_sensitive_claim_payload(claim, project_id))

    @app.post("/api/v1/admin/verification-issues/{issue_id}/resolve")
    def resolve_issue(
        issue_id: UUID,
        payload: VerificationIssueResolve,
        admin_id: UUID = Depends(require_admin_roles(*REVIEW_ADMIN_ROLES)),
        db: InMemoryStore = Depends(get_store),
    ) -> ApiResponse:
        issue = db.verification_issues.get(issue_id)
        if not issue:
            raise HTTPException(status_code=404, detail={"code": 40401, "message": "not found"})
        if not payload.resolution_reason.strip():
            raise HTTPException(status_code=422, detail={"code": 42201, "message": "resolution reason required"})
        from datetime import UTC, datetime

        issue["resolved_at"] = datetime.now(UTC).isoformat()
        issue["resolution_reason"] = payload.resolution_reason
        issue["resolved_by_admin_id"] = str(admin_id)
        db.save_verification_issue(issue_id, issue)
        if issue.get("project_id"):
            db.mark_verified_if_no_unresolved_blocks(UUID(str(issue["project_id"])))
        db.audit.record(
            AuditLog(
                actor_id=admin_id,
                action="admin.resolve_verification_issue",
                resource_type="verification_issue",
                resource_id=issue_id,
                reason=payload.resolution_reason,
            )
        )
        return ApiResponse(data=issue)

    @app.post("/api/v1/admin/tasks/{task_id}/retry")
    def retry_task(
        task_id: UUID,
        admin_id: UUID = Depends(require_admin_roles(*OPS_ADMIN_ROLES)),
        db: InMemoryStore = Depends(get_store),
    ) -> ApiResponse:
        db.audit.record(
            AuditLog(
                actor_id=admin_id,
                action="admin.retry_task",
                resource_type="task",
                resource_id=task_id,
            )
        )
        return ApiResponse(data={"task_id": str(task_id), "status": "queued"})

    @app.get("/api/v1/admin/alerts")
    def admin_alerts(_: UUID = Depends(current_admin_id), db: InMemoryStore = Depends(get_store)) -> ApiResponse:
        alerts = sorted(db.alerts.values(), key=lambda alert: alert.created_at, reverse=True)
        return ApiResponse(data={"alerts": [_alert_payload(alert) for alert in alerts]})

    @app.post("/api/v1/admin/alerts/simulate-500")
    def simulate_500(
        admin_id: UUID = Depends(require_admin_roles(*OPS_ADMIN_ROLES)),
        db: InMemoryStore = Depends(get_store),
    ) -> ApiResponse:
        db.audit.record(
            AuditLog(
                actor_id=admin_id,
                action="admin.simulate_500",
                resource_type="alert",
                metadata={"path": "/api/v1/admin/alerts/simulate-500"},
            )
        )
        raise RuntimeError("phase1 simulated alert")

    @app.get("/api/v1/admin/metrics/pilot")
    def pilot_metrics(_: UUID = Depends(current_admin_id), db: InMemoryStore = Depends(get_store)) -> ApiResponse:
        projects = list(db.projects.values())
        completed = [project for project in projects if project.status == "published"]
        feedback = list(db.feedback.values())
        recommend_values = [item.recommend for item in feedback if item.recommend is not None]
        nps_values = [item.nps_score for item in feedback if item.nps_score is not None]
        major_fact_errors = [item for item in feedback if item.issue_type == "major_fact_error"]
        manual_minutes = sum(item.minutes for item in db.manual_interventions.values())
        sessions = list(db.sessions.values())
        effective_sessions = [session for session in sessions if session.status == "completed"]
        p0_project_claims = [
            [
                db.claims[claim_id]
                for claim_id in claim_ids
                if claim_id in db.claims and db.claims[claim_id].is_p0
            ]
            for claim_ids in db.claims_by_project.values()
        ]
        p0_project_claims = [claims for claims in p0_project_claims if claims]
        processed_statuses = {"confirmed", "modified", "marked_unsure", "hidden", "deleted", "rejected"}
        family_corrected_projects = [
            claims
            for claims in p0_project_claims
            if all(claim.verification_status in processed_statuses for claim in claims)
        ]
        return ApiResponse(
            data={
                "households_total": len(projects),
                "completion_rate": len(completed) / len(projects) if projects else 0,
                "effective_interview_completion_rate": len(effective_sessions) / len(sessions) if sessions else 0,
                "family_correction_completion_rate": len(family_corrected_projects) / len(p0_project_claims) if p0_project_claims else 0,
                "major_fact_error_complaint_rate": len(major_fact_errors) / len(feedback) if feedback else 0,
                "recommend_rate": sum(1 for value in recommend_values if value) / len(recommend_values) if recommend_values else 0,
                "nps": sum(nps_values) / len(nps_values) if nps_values else None,
                "manual_minutes_per_household": manual_minutes / len(projects) if projects else None,
                "deposit_rate": len([p for p in projects if p.payment_status == "paid"]) / len(projects) if projects else 0,
                "feedback_count": len(feedback),
            }
        )

    @app.get("/api/v1/admin/exports/household-ops")
    def household_ops_export(_: UUID = Depends(current_admin_id), db: InMemoryStore = Depends(get_store)) -> ApiResponse:
        return ApiResponse(data={"households": [_household_ops_row(project, db) for project in db.projects.values()]})

    @app.get("/api/v1/admin/stuck-projects")
    def stuck_projects(_: UUID = Depends(current_admin_id), db: InMemoryStore = Depends(get_store)) -> ApiResponse:
        projects = [project for project in db.projects.values() if project.stuck_reason]
        return ApiResponse(data={"projects": [_project_payload(project) for project in projects]})

    @app.get("/api/v1/admin/support-tickets")
    def support_tickets(_: UUID = Depends(current_admin_id), db: InMemoryStore = Depends(get_store)) -> ApiResponse:
        tickets = sorted(db.support_tickets.values(), key=lambda ticket: ticket.created_at)
        return ApiResponse(data={"support_tickets": [_support_ticket_payload(ticket) for ticket in tickets]})

    @app.patch("/api/v1/admin/support-tickets/{ticket_id}")
    def patch_ticket(
        ticket_id: UUID,
        payload: SupportTicketPatch,
        admin_id: UUID = Depends(require_admin_roles(*OPS_ADMIN_ROLES)),
        db: InMemoryStore = Depends(get_store),
    ) -> ApiResponse:
        ticket = db.support_tickets.get(ticket_id)
        if not ticket:
            raise HTTPException(status_code=404, detail={"code": 40401, "message": "not found"})
        if payload.status:
            ticket.status = payload.status
        if payload.priority:
            ticket.priority = payload.priority
        if payload.admin_owner_id:
            ticket.admin_owner_id = payload.admin_owner_id
        ticket.updated_at = datetime.now(UTC)
        db.save_support_ticket(ticket)
        db.audit.record(
            AuditLog(
                actor_id=admin_id,
                action="admin.patch_support_ticket",
                resource_type="support_ticket",
                resource_id=ticket_id,
                metadata=payload.model_dump(mode="json", exclude_none=True),
            )
        )
        return ApiResponse(data=_support_ticket_payload(ticket))

    return app


def _default_code(status: int) -> int:
    return {400: 40001, 401: 40101, 403: 40301, 404: 40401, 409: 40901, 422: 42201, 429: 42901}.get(status, 50001)


def _configured_status(value: str | None) -> str:
    return "configured" if value else "missing"


def _validation_errors(exc: RequestValidationError) -> list[dict]:
    errors: list[dict] = []
    for error in exc.errors():
        clean_error = dict(error)
        ctx = clean_error.get("ctx")
        if isinstance(ctx, dict):
            clean_error["ctx"] = {key: str(value) for key, value in ctx.items()}
        errors.append(clean_error)
    return errors


def _websocket_user_id(websocket: WebSocket, db: InMemoryStore) -> UUID:
    claims = decode_token(websocket.headers.get("authorization"))
    ensure_token_active(claims, db)
    ensure_token_type(claims, "access")
    if claims.get("role") != "user":
        raise HTTPException(status_code=403, detail={"code": 40301, "message": "forbidden"})
    return UUID(str(claims["sub"]))


def _record_audio_chunk_payload(db: InMemoryStore, session, payload: AudioChunkUpload) -> dict:
    if not payload.oss_key.startswith(f"audio/{session.project_id}/"):
        raise ValueError("audio oss_key must be under the project audio prefix")
    expected_prefix = f"audio/{session.project_id}/interview-{session.id}-{payload.sequence_number}."
    if not payload.oss_key.startswith(expected_prefix):
        raise ValueError("audio oss_key must match the interview session and sequence")
    chunk = db.record_audio_chunk(
        session.id,
        payload.sequence_number,
        payload.duration_ms,
        payload.oss_key,
    )
    transcript_segment = None
    if payload.partial_transcript:
        transcript_segment = db.record_transcript_segment(
            session.project_id,
            session.id,
            payload.sequence_number,
            payload.speaker,
            payload.partial_transcript,
            payload.transcript_confidence if payload.transcript_confidence is not None else 1.0,
            payload.duration_ms,
        )
    recovery = db.session_recovery(session.id)
    return {
        "accepted": True,
        "session_id": str(session.id),
        "sequence_number": chunk.sequence_number,
        "transcript_segment_id": str(transcript_segment.id) if transcript_segment else None,
        "last_accepted_sequence_number": recovery["last_accepted_sequence_number"],
        "missing_sequence_numbers": recovery["missing_sequence_numbers"],
        "buffered_chunk_count": recovery["buffered_chunk_count"],
    }


def _audio_extension(content_type: str) -> str:
    normalized = content_type.split(";", 1)[0].strip().lower()
    return {
        "audio/mpeg": "mp3",
        "audio/mp3": "mp3",
        "audio/webm": "webm",
        "audio/wav": "wav",
        "audio/x-wav": "wav",
    }.get(normalized, "bin")


def _owned_project(db: InMemoryStore, project_id: UUID, user_id: UUID):
    project = db.projects.get(project_id)
    if not project or project.user_id != user_id or project.deleted_at:
        raise HTTPException(status_code=404, detail={"code": 40401, "message": "not found"})
    return project


def _admin_project(db: InMemoryStore, project_id: UUID):
    project = db.projects.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail={"code": 40401, "message": "not found"})
    return project


def _owned_session(db: InMemoryStore, session_id: UUID, user_id: UUID):
    session = db.sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail={"code": 40401, "message": "not found"})
    _owned_project(db, session.project_id, user_id)
    return session


def _claim_project_id(db: InMemoryStore, claim_id: UUID) -> UUID | None:
    for project_id, claim_ids in db.claims_by_project.items():
        if claim_id in claim_ids:
            return project_id
    return None


def _owned_claim(db: InMemoryStore, claim_id: UUID, user_id: UUID) -> ClaimDraft:
    claim = db.claims.get(claim_id)
    project_id = _claim_project_id(db, claim_id)
    if not claim or not project_id:
        raise HTTPException(status_code=404, detail={"code": 40401, "message": "not found"})
    _owned_project(db, project_id, user_id)
    return claim


def _owned_story_page_for_link(db: InMemoryStore, story_page_id: UUID, share_link_id: UUID, user_id: UUID):
    page = db.story_pages.get(story_page_id)
    link = db.share_links.get(share_link_id)
    if not page or not link or link.story_page_id != page.id:
        raise HTTPException(status_code=404, detail={"code": 40401, "message": "not found"})
    _owned_project(db, page.project_id, user_id)
    return page


def _active_story_link(db: InMemoryStore, page, share_token: str | None, password: str | None):
    if not page.share_links_enabled:
        raise HTTPException(status_code=403, detail={"code": 40301, "message": "story sharing is disabled"})
    link = db.active_share_link(page.id, share_token, password)
    if not link:
        raise HTTPException(status_code=403, detail={"code": 40301, "message": "valid share link required"})
    return link


def _story_page_payload(page, db: InMemoryStore, media_access_token: str) -> dict:
    chapters = []
    for chapter in page.draft.chapters if page.draft else []:
        chapter_payload = chapter.model_dump(mode="json")
        chapter_payload["audio_citations"] = _audio_citations(page.id, chapter.claim_ids, db, media_access_token)
        chapters.append(chapter_payload)
    comments = sorted(
        (comment for comment in db.family_comments.values() if comment.story_page_id == page.id and not comment.deleted_at),
        key=lambda comment: comment.created_at,
    )
    return {
        "story_page_id": str(page.id),
        "chapters": chapters,
        "comments": [_comment_payload(comment) for comment in comments],
    }


def _audio_citations(story_page_id: UUID, claim_ids: list[UUID], db: InMemoryStore, media_access_token: str) -> list[dict]:
    citations = []
    for claim_id in claim_ids:
        claim = db.claims.get(claim_id)
        if not claim:
            continue
        for segment_id in claim.source_segment_ids:
            citations.append(
                {
                    "claim_id": str(claim.id),
                    "segment_id": str(segment_id),
                    "starts_at_ms": 0,
                    "duration_ms": 15000,
                    "audio_url": f"/api/v1/story-pages/{story_page_id}/audio/{segment_id}?access_token={media_access_token}",
                }
            )
    return citations


def _story_has_segment(page, db: InMemoryStore, segment_id: UUID) -> bool:
    if not page.draft:
        return False
    claim_ids = {claim_id for chapter in page.draft.chapters for claim_id in chapter.claim_ids}
    return any(segment_id in claim.source_segment_ids for claim_id in claim_ids if (claim := db.claims.get(claim_id)))


def _share_link_payload(link, token: str | None = None) -> dict:
    return {
        "share_link_id": str(link.id),
        "story_page_id": str(link.story_page_id),
        "enabled": link.enabled,
        "password_protected": link.password_hash is not None,
        "share_token": token,
        "share_url": f"/api/v1/story-pages/{link.story_page_id}?share_token={token}" if token else None,
        "created_at": link.created_at,
        "revoked_at": link.revoked_at,
        "reset_at": link.reset_at,
    }


def _comment_payload(comment) -> dict:
    return {
        "comment_id": str(comment.id),
        "story_page_id": str(comment.story_page_id),
        "display_name": comment.display_name,
        "body": comment.body,
        "created_at": comment.created_at,
    }


def _feedback_payload(feedback) -> dict:
    return {
        "feedback_id": str(feedback.id),
        "project_id": str(feedback.project_id),
        "user_id": str(feedback.user_id),
        "nps_score": feedback.nps_score,
        "recommend": feedback.recommend,
        "issue_type": feedback.issue_type,
        "body": feedback.body,
        "created_at": feedback.created_at,
    }


def _support_ticket_payload(ticket) -> dict:
    return {
        "ticket_id": str(ticket.id),
        "project_id": str(ticket.project_id),
        "user_id": str(ticket.user_id) if ticket.user_id else None,
        "admin_owner_id": str(ticket.admin_owner_id) if ticket.admin_owner_id else None,
        "status": ticket.status,
        "priority": ticket.priority,
        "category": ticket.category,
        "body": ticket.body,
        "created_at": ticket.created_at,
        "updated_at": ticket.updated_at,
    }


def _claim_correction_payload(correction) -> dict:
    return {
        "correction_id": str(correction.id),
        "claim_id": str(correction.claim_id),
        "user_id": str(correction.user_id),
        "action": correction.action,
        "modified_text": correction.modified_text,
        "comment": correction.comment,
        "created_at": correction.created_at,
    }


def _internal_note_payload(note) -> dict:
    return {
        "note_id": str(note.id),
        "project_id": str(note.project_id),
        "admin_user_id": str(note.admin_user_id),
        "note_type": note.note_type,
        "body": note.body,
        "created_at": note.created_at,
    }


def _manual_intervention_payload(intervention) -> dict:
    return {
        "manual_intervention_id": str(intervention.id),
        "project_id": str(intervention.project_id),
        "admin_user_id": str(intervention.admin_user_id),
        "category": intervention.category,
        "minutes": intervention.minutes,
        "body": intervention.body,
        "created_at": intervention.created_at,
    }


def _ai_cost_payload(cost) -> dict:
    return {
        "ai_cost_id": str(cost.id),
        "project_id": str(cost.project_id),
        "admin_user_id": str(cost.admin_user_id),
        "task_type": cost.task_type,
        "provider": cost.provider,
        "cost_cents": cost.cost_cents,
        "generation_run_id": str(cost.generation_run_id) if cost.generation_run_id else None,
        "created_at": cost.created_at,
    }


def _alert_payload(alert) -> dict:
    return {
        "alert_id": str(alert.id),
        "path": alert.path,
        "method": alert.method,
        "error_type": alert.error_type,
        "message": alert.message,
        "created_at": alert.created_at,
    }


def _sensitive_claim_payload(claim, project_id: UUID) -> dict:
    payload = claim.model_dump(mode="json")
    payload["claim_id"] = str(claim.id)
    payload["project_id"] = str(project_id)
    return payload


def _admin_project_payload(project, db: InMemoryStore) -> dict:
    payload = _project_payload(project)
    project_session_ids = {session.id for session in db.sessions.values() if session.project_id == project.id}
    payload["audio_chunks"] = [
        _audio_chunk_payload(chunk)
        for chunk in sorted(db.audio_chunks.values(), key=lambda item: (str(item.session_id), item.sequence_number))
        if chunk.session_id in project_session_ids and not chunk.deleted_at
    ]
    payload["transcript_segments"] = [
        _transcript_segment_payload(segment)
        for segment in sorted(db.transcript_segments.values(), key=lambda item: (item.created_at, item.audio_chunk_sequence_number))
        if segment.project_id == project.id and not segment.deleted_at
    ]
    payload["internal_notes"] = [
        _internal_note_payload(note)
        for note in sorted(db.internal_notes.values(), key=lambda item: item.created_at)
        if note.project_id == project.id
    ]
    payload["manual_interventions"] = [
        _manual_intervention_payload(intervention)
        for intervention in sorted(db.manual_interventions.values(), key=lambda item: item.created_at)
        if intervention.project_id == project.id
    ]
    payload["ai_costs"] = [
        _ai_cost_payload(cost)
        for cost in sorted(db.ai_costs.values(), key=lambda item: item.created_at)
        if cost.project_id == project.id
    ]
    return payload


def _household_ops_row(project, db: InMemoryStore) -> dict:
    interventions = [item for item in db.manual_interventions.values() if item.project_id == project.id]
    costs = [item for item in db.ai_costs.values() if item.project_id == project.id]
    return {
        "project_id": str(project.id),
        "status": project.status,
        "payment_status": project.payment_status,
        "ai_cost_cents": sum(item.cost_cents for item in costs),
        "manual_intervention_count": len(interventions),
        "manual_minutes": sum(item.minutes for item in interventions),
        "ops_owner_id": str(project.ops_owner_id) if project.ops_owner_id else None,
        "stuck_reason": project.stuck_reason,
        "stuck_at": project.stuck_at,
    }


def _project_export_payload(project, db: InMemoryStore) -> dict:
    page = db.story_pages.get(project.story_page_id) if project.story_page_id else None
    project_claims = [
        db.claims[claim_id].model_dump(mode="json")
        for claim_id in db.claims_by_project.get(project.id, [])
        if claim_id in db.claims and not db.claims[claim_id].deleted_at
    ]
    project_session_ids = {session.id for session in db.sessions.values() if session.project_id == project.id}
    return {
        "project": _project_payload(project),
        "photos": [
            _photo_payload(photo)
            for photo in db.photos.values()
            if photo.project_id == project.id and not photo.deleted_at
        ],
        "claims": project_claims,
        "audio_chunks": [
            _audio_chunk_payload(chunk)
            for chunk in sorted(db.audio_chunks.values(), key=lambda item: (str(item.session_id), item.sequence_number))
            if chunk.session_id in project_session_ids and not chunk.deleted_at
        ],
        "transcript_segments": [
            _transcript_segment_payload(segment)
            for segment in sorted(db.transcript_segments.values(), key=lambda item: (item.created_at, item.audio_chunk_sequence_number))
            if segment.project_id == project.id and not segment.deleted_at
        ],
        "consents": [
            _consent_payload(consent)
            for consent in db.consent_records.values()
            if consent.project_id == project.id
        ],
        "story_page": _story_export_payload(page, db) if page and not page.deleted_at else None,
        "share_links": [
            _share_link_export_payload(link)
            for link in db.share_links.values()
            if page and link.story_page_id == page.id and not link.deleted_at
        ],
        "family_comments": [
            _comment_payload(comment)
            for comment in sorted(db.family_comments.values(), key=lambda item: item.created_at)
            if page and comment.story_page_id == page.id and not comment.deleted_at
        ],
        "pdf_exports": [
            _pdf_export_payload(pdf_export)
            for pdf_export in sorted(db.pdf_exports.values(), key=lambda item: item.created_at)
            if pdf_export.project_id == project.id and not pdf_export.deleted_at
        ],
        "feedback": [
            _feedback_payload(feedback)
            for feedback in sorted(db.feedback.values(), key=lambda item: item.created_at)
            if feedback.project_id == project.id
        ],
        "support_tickets": [
            _support_ticket_payload(ticket)
            for ticket in sorted(db.support_tickets.values(), key=lambda item: item.created_at)
            if ticket.project_id == project.id
        ],
    }


def _story_export_payload(page, db: InMemoryStore) -> dict:
    chapters = []
    for chapter in page.draft.chapters if page.draft else []:
        chapter_payload = chapter.model_dump(mode="json")
        chapter_payload["audio_citations"] = _audio_citations(page.id, chapter.claim_ids, db, "export")
        chapters.append(chapter_payload)
    return {
        "story_page_id": str(page.id),
        "enabled": page.enabled,
        "share_links_enabled": page.share_links_enabled,
        "chapters": chapters,
    }


def _photo_payload(photo) -> dict:
    return {
        "photo_id": str(photo.id),
        "project_id": str(photo.project_id),
        "oss_key": photo.oss_key,
        "thumbnail_oss_key": photo.thumbnail_oss_key,
        "caption": photo.caption,
        "deleted_at": photo.deleted_at,
        "purge_after_at": photo.purge_after_at,
    }


def _audio_chunk_payload(chunk) -> dict:
    return {
        "session_id": str(chunk.session_id),
        "sequence_number": chunk.sequence_number,
        "duration_ms": chunk.duration_ms,
        "oss_key": chunk.oss_key,
        "received_at": chunk.received_at,
        "deleted_at": chunk.deleted_at,
        "purge_after_at": chunk.purge_after_at,
    }


def _transcript_segment_payload(segment) -> dict:
    return {
        "transcript_segment_id": str(segment.id),
        "project_id": str(segment.project_id),
        "session_id": str(segment.session_id),
        "audio_chunk_sequence_number": segment.audio_chunk_sequence_number,
        "speaker": segment.speaker,
        "text": segment.text,
        "start_ms": segment.start_ms,
        "end_ms": segment.end_ms,
        "confidence": segment.confidence,
        "low_confidence_review": segment.low_confidence_review,
        "created_at": segment.created_at,
        "deleted_at": segment.deleted_at,
        "purge_after_at": segment.purge_after_at,
    }


def _photo_analysis_payload(analysis) -> dict:
    return {
        "photo_analysis_id": str(analysis.id),
        "project_id": str(analysis.project_id),
        "photo_id": str(analysis.photo_id),
        "hypothesis_text": analysis.hypothesis_text,
        "confidence": analysis.confidence,
        "internal_only": analysis.internal_only,
        "eligible_for_prompt": analysis.eligible_for_prompt,
        "converted_claim_id": str(analysis.converted_claim_id) if analysis.converted_claim_id else None,
        "created_at": analysis.created_at,
        "deleted_at": analysis.deleted_at,
        "purge_after_at": analysis.purge_after_at,
    }


def _has_photo_uncertainty(text: str) -> bool:
    return any(marker in text for marker in ("可能", "大约", "推测"))


def _pdf_export_payload(pdf_export) -> dict:
    return {
        "pdf_export_id": str(pdf_export.id),
        "project_id": str(pdf_export.project_id),
        "story_page_id": str(pdf_export.story_page_id),
        "oss_key": pdf_export.oss_key,
        "created_at": pdf_export.created_at,
        "deleted_at": pdf_export.deleted_at,
        "purge_after_at": pdf_export.purge_after_at,
    }


def _consent_payload(consent) -> dict:
    return {
        "consent_id": str(consent.id),
        "project_id": str(consent.project_id),
        "user_id": str(consent.user_id) if consent.user_id else None,
        "consent_type": consent.consent_type,
        "method": consent.method,
        "evidence_oss_key": consent.evidence_oss_key,
        "withdrawn_at": consent.withdrawn_at,
        "minimized_at": consent.minimized_at,
        "created_at": consent.created_at,
    }


def _share_link_export_payload(link) -> dict:
    return {
        "share_link_id": str(link.id),
        "story_page_id": str(link.story_page_id),
        "enabled": link.enabled,
        "password_protected": link.password_hash is not None,
        "created_at": link.created_at,
        "revoked_at": link.revoked_at,
        "reset_at": link.reset_at,
    }


def _project_payload(project) -> dict:
    return {
        "project_id": str(project.id),
        "title": project.title,
        "status": project.status,
        "storyteller": project.storyteller,
        "themes": project.themes,
        "tier": project.tier,
        "payment_status": project.payment_status,
        "payment_cents": project.payment_cents,
        "payment_method": project.payment_method,
        "payment_reference": project.payment_reference,
        "story_page_id": str(project.story_page_id) if project.story_page_id else None,
        "ops_owner_id": str(project.ops_owner_id) if project.ops_owner_id else None,
        "stuck_reason": project.stuck_reason,
        "stuck_at": project.stuck_at,
        "created_at": project.created_at,
        "updated_at": project.updated_at,
        "deleted_at": project.deleted_at,
        "purge_after_at": project.purge_after_at,
    }


def _deletion_request_payload(deletion: DeletionRequestRecord) -> dict:
    return {
        "deletion_request_id": str(deletion.id),
        "project_id": str(deletion.project_id),
        "requested_at": deletion.requested_at,
        "execute_after_at": deletion.execute_after_at,
        "executed_at": deletion.executed_at,
        "status": deletion.status,
    }


app = create_app()
