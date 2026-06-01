import { request } from "../../utils/api";

type PhotoPresignResponse = {
  upload_url: string;
  oss_key: string;
  headers: Record<string, string>;
};

type PhotoCompleteResponse = {
  photo_id: string;
  thumbnail_oss_key: string;
  photo_count: number;
  internal_photo_hypothesis_only: boolean;
};

type ProjectPhoto = {
  id?: string;
  photo_id: string;
  oss_key: string;
  thumbnail_oss_key?: string;
  caption?: string | null;
};

type PhotoListResponse = {
  photos: Array<ProjectPhoto & { id?: string }>;
};

Page({
  data: {
    title: "爸爸的故事",
    displayName: "爸爸",
    relation: "father",
    projectId: "",
    photoCaption: "",
    minimumPhotoCount: 3,
    maxPhotoCount: 10,
    photoCount: 0,
    photos: [] as ProjectPhoto[],
    uploadingPhotos: false,
    loadingPhotos: false,
    internalPhotoHypothesisOnly: true,
    statusMessage: "",
    errorMessage: ""
  },
  onTitle(event: WechatMiniprogram.Input) {
    this.setData({ title: event.detail.value });
  },
  onDisplayName(event: WechatMiniprogram.Input) {
    this.setData({ displayName: event.detail.value });
  },
  onRelation(event: WechatMiniprogram.Input) {
    this.setData({ relation: event.detail.value });
  },
  onPhotoCaption(event: WechatMiniprogram.Input) {
    this.setData({ photoCaption: event.detail.value });
  },
  async createProject() {
    this.setData({ errorMessage: "", statusMessage: "" });
    try {
      const data = await request<{ project_id: string }>("/api/v1/projects", "POST", {
        title: this.data.title,
        tier: "standard",
        themes: ["childhood", "work", "family"],
        storyteller: {
          display_name: this.data.displayName,
          relation_to_payer: this.data.relation,
          primary_dialect: "mandarin"
        }
      });
      this.setData({ projectId: data.project_id, statusMessage: "项目已创建，请上传 3-10 张照片后发起采访。" });
      await this.loadPhotos();
    } catch (error) {
      this.setData({ errorMessage: (error as Error).message });
    }
  },
  pickAndUploadPhotos() {
    if (!this.ensureProjectId()) return;
    const remaining = this.data.maxPhotoCount - this.data.photoCount;
    if (remaining <= 0) {
      this.setData({ errorMessage: "每个项目最多上传 10 张照片" });
      return;
    }
    wx.chooseMedia({
      count: remaining,
      mediaType: ["image"],
      sourceType: ["album", "camera"],
      sizeType: ["compressed"],
      success: (result) => {
        void this.uploadSelectedPhotos(result.tempFiles);
      },
      fail: (error) => this.setData({ errorMessage: error.errMsg })
    });
  },
  async uploadSelectedPhotos(tempFiles: WechatMiniprogram.MediaFile[]) {
    this.setData({ uploadingPhotos: true, errorMessage: "", statusMessage: "" });
    try {
      for (const file of tempFiles) {
        if (this.data.photoCount >= this.data.maxPhotoCount) break;
        const filename = fileNameFromPath(file.tempFilePath);
        const presign = await request<PhotoPresignResponse>(
          `/api/v1/projects/${this.data.projectId}/photos/presign`,
          "POST",
          { filename, content_type: contentTypeFor(filename) }
        );
        await uploadFileToOss(presign.upload_url, file.tempFilePath, presign.headers);
        const completed = await request<PhotoCompleteResponse>(
          `/api/v1/projects/${this.data.projectId}/photos/complete`,
          "POST",
          { oss_key: presign.oss_key, caption: this.data.photoCaption || null }
        );
        this.setData({
          photoCount: completed.photo_count,
          internalPhotoHypothesisOnly: completed.internal_photo_hypothesis_only,
          statusMessage: `已上传 ${completed.photo_count} 张照片`
        });
      }
      await this.loadPhotos();
    } catch (error) {
      this.setData({ uploadingPhotos: false, errorMessage: (error as Error).message });
    }
  },
  async loadPhotos() {
    if (!this.ensureProjectId()) return;
    this.setData({ loadingPhotos: true, errorMessage: "" });
    try {
      const data = await request<PhotoListResponse>(`/api/v1/projects/${this.data.projectId}/photos`, "GET");
      const photos = normalizePhotos(data.photos);
      this.setData({
        photos,
        photoCount: photos.length,
        loadingPhotos: false,
        uploadingPhotos: false,
        statusMessage: photos.length >= this.data.minimumPhotoCount ? "照片数量已满足采访前置条件" : this.data.statusMessage
      });
    } catch (error) {
      this.setData({ loadingPhotos: false, uploadingPhotos: false, errorMessage: (error as Error).message });
    }
  },
  deletePhoto(event: WechatMiniprogram.TouchEvent) {
    const photoId = String(event.currentTarget.dataset.id || "");
    if (!photoId) return;
    wx.showModal({
      title: "删除照片",
      content: "删除后照片会从采访准备材料中移除。",
      confirmText: "删除",
      confirmColor: "#a5453d",
      success: (result) => {
        if (result.confirm) {
          void this.performDeletePhoto(photoId);
        }
      }
    });
  },
  async performDeletePhoto(photoId: string) {
    this.setData({ loadingPhotos: true, errorMessage: "", statusMessage: "" });
    try {
      await request<{ deleted: boolean }>(`/api/v1/photos/${photoId}`, "DELETE");
      await this.loadPhotos();
      this.setData({ statusMessage: "照片已删除" });
    } catch (error) {
      this.setData({ loadingPhotos: false, errorMessage: (error as Error).message });
    }
  },
  ensureProjectId() {
    if (this.data.projectId) return true;
    this.setData({ errorMessage: "请先创建项目" });
    return false;
  }
});

function uploadFileToOss(url: string, filePath: string, headers: Record<string, string>) {
  return new Promise<void>((resolve, reject) => {
    wx.uploadFile({
      url,
      filePath,
      name: "file",
      header: headers,
      success(response) {
        if (response.statusCode >= 200 && response.statusCode < 300) {
          resolve();
        } else {
          reject(new Error(`photo upload failed: ${response.statusCode}`));
        }
      },
      fail: reject
    });
  });
}

function normalizePhotos(photos: Array<ProjectPhoto & { id?: string }>): ProjectPhoto[] {
  return photos.map((photo) => ({
    ...photo,
    photo_id: photo.photo_id || photo.id || ""
  }));
}

function fileNameFromPath(filePath: string): string {
  const parts = filePath.split("/");
  return parts[parts.length - 1] || `family-photo-${Date.now()}.jpg`;
}

function contentTypeFor(filename: string): string {
  const lower = filename.toLowerCase();
  if (lower.endsWith(".png")) return "image/png";
  if (lower.endsWith(".webp")) return "image/webp";
  return "image/jpeg";
}
