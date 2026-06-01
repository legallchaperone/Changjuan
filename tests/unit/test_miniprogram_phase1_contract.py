from __future__ import annotations

from pathlib import Path


def test_miniprogram_index_supports_login_and_mvp_navigation() -> None:
    page_ts = Path("miniprogram/pages/index/index.ts").read_text()
    page_wxml = Path("miniprogram/pages/index/index.wxml").read_text()
    app_ts = Path("miniprogram/app.ts").read_text()

    assert "wx.login" in page_ts
    assert "/api/v1/auth/wx-login" in page_ts
    assert "wx_code: wxCode" in page_ts
    assert "wx_openid: this.data.wxOpenid || wxCode" not in page_ts
    assert "wxOpenid" not in page_ts
    assert "内测 openid" not in page_wxml
    assert "access_token" in page_ts
    assert "refresh_token" in page_ts
    assert "app.globalData.accessToken" in page_ts
    assert "app.globalData.refreshToken" in page_ts
    assert 'wx.setStorageSync("access_token"' in page_ts
    assert 'wx.setStorageSync("refresh_token"' in page_ts
    assert "refreshToken" in app_ts
    assert 'bindtap="login"' in page_wxml
    assert 'url="/pages/project/project"' in page_wxml
    assert 'url="/pages/interview/interview?project_id={{projectId}}"' in page_wxml
    assert 'url="/pages/corrections/corrections?project_id={{projectId}}"' in page_wxml
    assert 'url="/pages/story/story?project_id={{projectId}}&story_page_id={{storyPageId}}"' in page_wxml
    assert 'url="/pages/privacy/privacy?project_id={{projectId}}"' in page_wxml


def test_miniprogram_project_page_supports_photo_upload_lifecycle() -> None:
    page_ts = Path("miniprogram/pages/project/project.ts").read_text()
    page_wxml = Path("miniprogram/pages/project/project.wxml").read_text()

    assert "minimumPhotoCount: 3" in page_ts
    assert "maxPhotoCount: 10" in page_ts
    assert "wx.chooseMedia" in page_ts
    assert "wx.uploadFile" in page_ts
    assert "/api/v1/projects/${this.data.projectId}/photos/presign" in page_ts
    assert "/api/v1/projects/${this.data.projectId}/photos/complete" in page_ts
    assert "/api/v1/projects/${this.data.projectId}/photos" in page_ts
    assert "/api/v1/photos/${photoId}" in page_ts
    assert "photo_count" in page_ts
    assert "internal_photo_hypothesis_only" in page_ts
    assert 'bindtap="pickAndUploadPhotos"' in page_wxml
    assert 'bindtap="loadPhotos"' in page_wxml
    assert 'bindtap="deletePhoto"' in page_wxml


def test_miniprogram_corrections_page_supports_phase1_family_actions() -> None:
    page_ts = Path("miniprogram/pages/corrections/corrections.ts").read_text()
    page_wxml = Path("miniprogram/pages/corrections/corrections.wxml").read_text()

    assert "/api/v1/projects/${this.data.projectId}/corrections/pending" in page_ts
    assert "pendingLimit: 20" in page_ts
    assert "sortClaims" in page_ts
    assert 'action: "confirm"' in page_ts
    assert 'action: "modify"' in page_ts
    assert 'action: "unsure"' in page_ts
    assert 'action: "hide_from_family"' in page_ts
    assert 'action: "delete"' in page_ts
    assert "/api/v1/claims/${claimId}/corrections" in page_ts
    assert 'bindtap="confirm"' in page_wxml
    assert 'bindtap="modify"' in page_wxml
    assert 'bindtap="unsure"' in page_wxml
    assert 'bindtap="hide"' in page_wxml
    assert 'bindtap="deleteClaim"' in page_wxml


def test_miniprogram_privacy_page_supports_export_delete_and_status() -> None:
    page_ts = Path("miniprogram/pages/privacy/privacy.ts").read_text()
    page_wxml = Path("miniprogram/pages/privacy/privacy.wxml").read_text()

    assert "/api/v1/projects/${this.data.projectId}/export" in page_ts
    assert "/api/v1/projects/${this.data.projectId}" in page_ts
    assert '"DELETE"' in page_ts
    assert "/api/v1/projects/${this.data.projectId}/deletion-request" in page_ts
    assert "deletionRequestId" in page_ts
    assert 'bindtap="exportProject"' in page_wxml
    assert 'bindtap="requestDeletion"' in page_wxml
    assert 'bindtap="checkDeletionStatus"' in page_wxml


def test_miniprogram_story_page_supports_story_share_audio_pdf_and_second_consent() -> None:
    page_ts = Path("miniprogram/pages/story/story.ts").read_text()
    page_wxml = Path("miniprogram/pages/story/story.wxml").read_text()

    assert "/api/v1/story-pages/${this.data.storyPageId}" in page_ts
    assert "/api/v1/story-pages/${this.data.storyPageId}/share-links" in page_ts
    assert "/api/v1/story-pages/${this.data.storyPageId}/share-links/${this.data.shareLinkId}" in page_ts
    assert "/api/v1/story-pages/${this.data.storyPageId}/share-links/${this.data.shareLinkId}/reset" in page_ts
    assert "/api/v1/story-pages/${this.data.storyPageId}/pdf-export" in page_ts
    assert "/api/v1/projects/${this.data.projectId}/request-second-consent" in page_ts
    assert "wx.createInnerAudioContext" in page_ts
    assert "wx.downloadFile" in page_ts
    assert "audio_url" in page_ts
    assert 'bindtap="loadStory"' in page_wxml
    assert 'bindtap="playAudio"' in page_wxml
    assert 'bindtap="createShareLink"' in page_wxml
    assert 'bindtap="revokeShareLink"' in page_wxml
    assert 'bindtap="resetShareLink"' in page_wxml
    assert 'bindtap="exportPdf"' in page_wxml
    assert 'bindtap="requestSecondConsent"' in page_wxml


def test_miniprogram_interview_page_supports_consent_session_audio_and_recovery() -> None:
    page_ts = Path("miniprogram/pages/interview/interview.ts").read_text()
    page_wxml = Path("miniprogram/pages/interview/interview.wxml").read_text()

    assert "/api/v1/projects/${this.data.projectId}/consents" in page_ts
    assert 'consent_type: "interview_consent"' in page_ts
    assert "/api/v1/projects/${this.data.projectId}/interview-sessions" in page_ts
    assert "/api/v1/interview-sessions/${this.data.sessionId}/start" in page_ts
    assert "/api/v1/interview-sessions/${this.data.sessionId}/end" in page_ts
    assert "/api/v1/interview-sessions/${this.data.sessionId}/stream" in page_ts
    assert "if (!this.ensureProjectId() || !this.ensureSessionId()) return;" in page_ts
    assert "wx.connectSocket" in page_ts
    assert "socketTask.send" in page_ts
    assert "socketTask.close" in page_ts
    assert "/api/v1/interview-sessions/${this.data.sessionId}/audio-chunks/presign" in page_ts
    assert "wx.request" in page_ts
    assert 'method: "PUT"' in page_ts
    assert "data: frameBuffer" in page_ts
    assert "/api/v1/interview-sessions/${this.data.sessionId}/audio-chunks`" not in page_ts
    assert "/api/v1/interview-sessions/${this.data.sessionId}/recovery" in page_ts
    assert "wx.getRecorderManager" in page_ts
    assert "onFrameRecorded" in page_ts
    assert "duration_ms: 500" in page_ts
    assert "sequence_number" in page_ts
    assert "oss_key: presign.oss_key" in page_ts
    assert "oss_key: `audio/${this.data.sessionId}/" not in page_ts
    assert 'bindtap="createConsent"' in page_wxml
    assert 'bindtap="createSession"' in page_wxml
    assert 'bindtap="startInterview"' in page_wxml
    assert 'bindtap="endInterview"' in page_wxml
    assert 'bindtap="checkRecovery"' in page_wxml
