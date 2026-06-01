import { request } from "../../utils/api";

type ConsentResponse = {
  consent_id: string;
};

type InterviewSessionResponse = {
  session_id: string;
  status: string;
};

type AudioChunkUploadResponse = {
  accepted: boolean;
  last_accepted_sequence_number: number | null;
  missing_sequence_numbers: number[];
};

type AudioChunkPresignResponse = {
  upload_url: string;
  oss_key: string;
  headers: Record<string, string>;
};

type SessionRecoveryResponse = {
  last_accepted_sequence_number: number | null;
  missing_sequence_numbers: number[];
  buffered_chunk_count: number;
};

const app = getApp<{
  globalData: {
    apiBaseUrl: string;
    accessToken: string;
  };
}>();

let recorder: WechatMiniprogram.RecorderManager | null = null;
let socketTask: WechatMiniprogram.SocketTask | null = null;
let socketOpen = false;

Page({
  data: {
    projectId: "",
    sessionId: "",
    consentId: "",
    recording: false,
    sequenceNumber: 0,
    statusMessage: "",
    errorMessage: "",
    missingSequenceNumbers: [] as number[]
  },
  onLoad(options: Record<string, string | undefined>) {
    this.setData({ projectId: options.project_id || "" });
    recorder = wx.getRecorderManager();
    recorder.onFrameRecorded((frame) => {
      void this.uploadAudioFrame(frame.frameBuffer);
    });
    recorder.onError((error) => {
      this.setData({ errorMessage: error.errMsg, recording: false });
      this.closeInterviewStream();
    });
  },
  onProjectId(event: WechatMiniprogram.Input) {
    this.setData({ projectId: event.detail.value });
  },
  async createConsent() {
    if (!this.ensureProjectId()) return;
    this.setData({ errorMessage: "", statusMessage: "" });
    try {
      const data = await request<ConsentResponse>(
        `/api/v1/projects/${this.data.projectId}/consents`,
        "POST",
        { consent_type: "interview_consent", method: "text" }
      );
      this.setData({ consentId: data.consent_id, statusMessage: "采访同意已记录" });
    } catch (error) {
      this.setData({ errorMessage: (error as Error).message });
    }
  },
  async createSession() {
    if (!this.ensureProjectId()) return;
    this.setData({ errorMessage: "", statusMessage: "" });
    try {
      const data = await request<InterviewSessionResponse>(
        `/api/v1/projects/${this.data.projectId}/interview-sessions`,
        "POST",
        {}
      );
      this.setData({ sessionId: data.session_id, statusMessage: `采访会话：${data.status}` });
    } catch (error) {
      this.setData({ errorMessage: (error as Error).message });
    }
  },
  async startInterview() {
    if (!this.ensureProjectId() || !this.ensureSessionId()) return;
    this.setData({ errorMessage: "", statusMessage: "" });
    try {
      const data = await request<InterviewSessionResponse>(
        `/api/v1/interview-sessions/${this.data.sessionId}/start`,
        "POST",
        {}
      );
      this.openInterviewStream(() => {
        recorder?.start({
          duration: 40 * 60 * 1000,
          sampleRate: 16000,
          numberOfChannels: 1,
          encodeBitRate: 48000,
          format: "mp3",
          frameSize: 1
        });
        this.setData({ recording: true, statusMessage: `采访状态：${data.status}` });
      });
    } catch (error) {
      this.setData({ errorMessage: (error as Error).message });
    }
  },
  async endInterview() {
    if (!this.ensureSessionId()) return;
    recorder?.stop();
    this.closeInterviewStream();
    this.setData({ errorMessage: "", recording: false });
    try {
      const data = await request<InterviewSessionResponse>(
        `/api/v1/interview-sessions/${this.data.sessionId}/end`,
        "POST",
        { status: "completed_short" }
      );
      this.setData({ statusMessage: `采访状态：${data.status}` });
    } catch (error) {
      this.setData({ errorMessage: (error as Error).message });
    }
  },
  openInterviewStream(onOpen: () => void) {
    this.closeInterviewStream();
    const wsBaseUrl = app.globalData.apiBaseUrl.replace(/^http:/, "ws:").replace(/^https:/, "wss:");
    socketTask = wx.connectSocket({
      url: `${wsBaseUrl}/api/v1/interview-sessions/${this.data.sessionId}/stream`,
      header: app.globalData.accessToken
        ? { Authorization: `Bearer ${app.globalData.accessToken}` }
        : {}
    });
    socketTask.onOpen(() => {
      socketOpen = true;
      onOpen();
    });
    socketTask.onMessage((message) => {
      this.handleStreamMessage(message.data);
    });
    socketTask.onError((error) => {
      socketOpen = false;
      this.setData({ errorMessage: error.errMsg, recording: false });
      recorder?.stop();
    });
    socketTask.onClose(() => {
      socketOpen = false;
    });
  },
  closeInterviewStream() {
    socketOpen = false;
    if (socketTask) {
      socketTask.close({});
    }
    socketTask = null;
  },
  async uploadAudioFrame(frameBuffer: ArrayBuffer) {
    if (!this.data.projectId || !this.data.sessionId || !this.data.recording || !socketTask || !socketOpen) return;
    const sequenceNumber = this.data.sequenceNumber;
    this.setData({ sequenceNumber: sequenceNumber + 1 });
    try {
      const presign = await request<AudioChunkPresignResponse>(
        `/api/v1/interview-sessions/${this.data.sessionId}/audio-chunks/presign`,
        "POST",
        { sequence_number: sequenceNumber, content_type: "audio/mpeg" }
      );
      await this.uploadAudioBytes(presign, frameBuffer);
      socketTask.send({
        data: JSON.stringify({
          sequence_number: sequenceNumber,
          duration_ms: 500,
          oss_key: presign.oss_key,
          speaker: "storyteller"
        }),
        fail: (error) => {
          this.setData({ errorMessage: error.errMsg });
        }
      });
    } catch (error) {
      this.setData({ errorMessage: (error as Error).message });
    }
  },
  uploadAudioBytes(presign: AudioChunkPresignResponse, frameBuffer: ArrayBuffer) {
    return new Promise<void>((resolve, reject) => {
      wx.request({
        url: presign.upload_url,
        method: "PUT",
        data: frameBuffer,
        header: presign.headers,
        success(response) {
          if (response.statusCode >= 200 && response.statusCode < 300) {
            resolve();
          } else {
            reject(new Error(`audio upload failed: ${response.statusCode}`));
          }
        },
        fail(error) {
          reject(new Error(error.errMsg));
        }
      });
    });
  },
  handleStreamMessage(rawData: string | ArrayBuffer) {
    if (typeof rawData !== "string") return;
    const data = JSON.parse(rawData) as Partial<AudioChunkUploadResponse>;
    if (data.accepted === undefined) return;
    if (data.accepted) {
      this.setData({
        missingSequenceNumbers: data.missing_sequence_numbers || [],
        statusMessage: "音频 chunk 已上传"
      });
    } else {
      this.setData({ statusMessage: "音频 chunk 待重试" });
    }
  },
  async checkRecovery() {
    if (!this.ensureSessionId()) return;
    this.setData({ errorMessage: "" });
    try {
      const data = await request<SessionRecoveryResponse>(
        `/api/v1/interview-sessions/${this.data.sessionId}/recovery`,
        "GET"
      );
      this.setData({
        missingSequenceNumbers: data.missing_sequence_numbers,
        statusMessage: `已缓存 ${data.buffered_chunk_count} 个 chunk`
      });
    } catch (error) {
      this.setData({ errorMessage: (error as Error).message });
    }
  },
  ensureProjectId() {
    if (this.data.projectId) return true;
    this.setData({ errorMessage: "请先填写 project_id" });
    return false;
  },
  ensureSessionId() {
    if (this.data.sessionId) return true;
    this.setData({ errorMessage: "请先创建采访会话" });
    return false;
  }
});
