import { request } from "../../utils/api";

type AudioCitation = {
  claim_id: string;
  segment_id: string;
  starts_at_ms: number;
  duration_ms: number;
  audio_url: string;
};

type StoryChapter = {
  id: string;
  title: string;
  body: string;
  claim_ids: string[];
  audio_citations: AudioCitation[];
};

type StoryPageResponse = {
  story_page_id: string;
  chapters: StoryChapter[];
};

type ShareLinkResponse = {
  share_link_id: string;
  share_token: string | null;
  share_url: string | null;
  enabled: boolean;
  password_protected: boolean;
};

const app = getApp<{ globalData: { apiBaseUrl: string; accessToken: string } }>();

Page({
  data: {
    projectId: "",
    storyPageId: "",
    shareToken: "",
    password: "",
    shareLinkId: "",
    shareUrl: "",
    chapters: [] as StoryChapter[],
    loading: false,
    errorMessage: "",
    statusMessage: ""
  },
  onLoad(options: Record<string, string | undefined>) {
    this.setData({
      projectId: options.project_id || "",
      storyPageId: options.story_page_id || "",
      shareToken: options.share_token || "",
      password: options.password || ""
    });
    if (options.story_page_id) {
      void this.loadStory();
    }
  },
  onStoryPageId(event: WechatMiniprogram.Input) {
    this.setData({ storyPageId: event.detail.value });
  },
  onProjectId(event: WechatMiniprogram.Input) {
    this.setData({ projectId: event.detail.value });
  },
  onPassword(event: WechatMiniprogram.Input) {
    this.setData({ password: event.detail.value });
  },
  async loadStory() {
    if (!this.ensureStoryPageId()) return;
    this.setData({ loading: true, errorMessage: "", statusMessage: "" });
    try {
      const query = this.storyAccessQuery();
      const data = await request<StoryPageResponse>(
        `/api/v1/story-pages/${this.data.storyPageId}${query}`,
        "GET"
      );
      this.setData({ chapters: data.chapters, loading: false });
    } catch (error) {
      this.setData({ loading: false, errorMessage: (error as Error).message });
    }
  },
  playAudio(event: WechatMiniprogram.TouchEvent) {
    const chapterIndex = Number(event.currentTarget.dataset.chapterIndex || 0);
    const citationIndex = Number(event.currentTarget.dataset.citationIndex || 0);
    const citation = this.data.chapters[chapterIndex]?.audio_citations[citationIndex];
    if (!citation?.audio_url) return;
    const audio = wx.createInnerAudioContext();
    audio.src = `${app.globalData.apiBaseUrl}${citation.audio_url}`;
    audio.play();
    this.setData({ statusMessage: "正在播放原声引用" });
  },
  async createShareLink() {
    if (!this.ensureStoryPageId()) return;
    this.setData({ loading: true, errorMessage: "", statusMessage: "" });
    try {
      const data = await request<ShareLinkResponse>(
        `/api/v1/story-pages/${this.data.storyPageId}/share-links`,
        "POST",
        this.data.password ? { password: this.data.password } : {}
      );
      this.setShareLink(data, "分享链接已创建");
    } catch (error) {
      this.setData({ loading: false, errorMessage: (error as Error).message });
    }
  },
  async revokeShareLink() {
    if (!this.ensureShareLink()) return;
    this.setData({ loading: true, errorMessage: "", statusMessage: "" });
    try {
      const data = await request<ShareLinkResponse>(
        `/api/v1/story-pages/${this.data.storyPageId}/share-links/${this.data.shareLinkId}`,
        "DELETE"
      );
      this.setShareLink(data, "分享链接已关闭");
    } catch (error) {
      this.setData({ loading: false, errorMessage: (error as Error).message });
    }
  },
  async resetShareLink() {
    if (!this.ensureShareLink()) return;
    this.setData({ loading: true, errorMessage: "", statusMessage: "" });
    try {
      const data = await request<ShareLinkResponse>(
        `/api/v1/story-pages/${this.data.storyPageId}/share-links/${this.data.shareLinkId}/reset`,
        "POST"
      );
      this.setShareLink(data, "分享链接已重置");
    } catch (error) {
      this.setData({ loading: false, errorMessage: (error as Error).message });
    }
  },
  exportPdf() {
    if (!this.ensureStoryPageId()) return;
    const query = this.storyAccessQuery();
    const header = app.globalData.accessToken ? { Authorization: `Bearer ${app.globalData.accessToken}` } : {};
    wx.downloadFile({
      url: `${app.globalData.apiBaseUrl}/api/v1/story-pages/${this.data.storyPageId}/pdf-export${query}`,
      header,
      success: () => this.setData({ statusMessage: "PDF 已生成", errorMessage: "" }),
      fail: (error) => this.setData({ errorMessage: error.errMsg })
    });
  },
  async requestSecondConsent() {
    if (!this.data.projectId) {
      this.setData({ errorMessage: "请先填写 project_id" });
      return;
    }
    this.setData({ loading: true, errorMessage: "", statusMessage: "" });
    try {
      await request<{ status: string }>(
        `/api/v1/projects/${this.data.projectId}/request-second-consent`,
        "POST"
      );
      this.setData({ loading: false, statusMessage: "已进入二次同意流程" });
    } catch (error) {
      this.setData({ loading: false, errorMessage: (error as Error).message });
    }
  },
  storyAccessQuery() {
    const params: string[] = [];
    if (this.data.shareToken) params.push(`share_token=${encodeURIComponent(this.data.shareToken)}`);
    if (this.data.password) params.push(`password=${encodeURIComponent(this.data.password)}`);
    return params.length ? `?${params.join("&")}` : "";
  },
  setShareLink(data: ShareLinkResponse, statusMessage: string) {
    this.setData({
      loading: false,
      shareLinkId: data.share_link_id,
      shareToken: data.share_token || this.data.shareToken,
      shareUrl: data.share_url || "",
      statusMessage
    });
  },
  ensureStoryPageId() {
    if (this.data.storyPageId) return true;
    this.setData({ errorMessage: "请先填写 story_page_id" });
    return false;
  },
  ensureShareLink() {
    if (this.ensureStoryPageId() && this.data.shareLinkId) return true;
    this.setData({ errorMessage: "请先创建分享链接" });
    return false;
  }
});
