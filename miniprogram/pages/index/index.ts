import { request } from "../../utils/api";

type WxLoginResponse = {
  access_token: string;
  refresh_token: string;
  user_id: string;
};

const app = getApp<{
  globalData: {
    apiBaseUrl: string;
    accessToken: string;
    refreshToken: string;
    userId: string;
  };
}>();

Page({
  data: {
    nickname: "女儿",
    projectId: "",
    storyPageId: "",
    loggedIn: false,
    userId: "",
    loading: false,
    statusMessage: "",
    errorMessage: ""
  },
  onLoad() {
    const accessToken = wx.getStorageSync("access_token") || "";
    const refreshToken = wx.getStorageSync("refresh_token") || "";
    const userId = wx.getStorageSync("user_id") || "";
    app.globalData.accessToken = accessToken;
    app.globalData.refreshToken = refreshToken;
    app.globalData.userId = userId;
    this.setData({
      loggedIn: Boolean(accessToken),
      userId,
      statusMessage: accessToken ? "已登录" : ""
    });
  },
  onNickname(event: WechatMiniprogram.Input) {
    this.setData({ nickname: event.detail.value });
  },
  onProjectId(event: WechatMiniprogram.Input) {
    this.setData({ projectId: event.detail.value });
  },
  onStoryPageId(event: WechatMiniprogram.Input) {
    this.setData({ storyPageId: event.detail.value });
  },
  login() {
    this.setData({ loading: true, errorMessage: "", statusMessage: "" });
    wx.login({
      success: (loginResult) => {
        void this.exchangeLogin(loginResult.code);
      },
      fail: (error) => this.setData({ loading: false, errorMessage: error.errMsg })
    });
  },
  async exchangeLogin(wxCode: string) {
    try {
      const data = await request<WxLoginResponse>("/api/v1/auth/wx-login", "POST", {
        wx_code: wxCode,
        nickname: this.data.nickname
      });
      app.globalData.accessToken = data.access_token;
      app.globalData.refreshToken = data.refresh_token;
      app.globalData.userId = data.user_id;
      wx.setStorageSync("access_token", data.access_token);
      wx.setStorageSync("refresh_token", data.refresh_token);
      wx.setStorageSync("user_id", data.user_id);
      this.setData({
        loggedIn: true,
        userId: data.user_id,
        loading: false,
        statusMessage: "登录成功"
      });
    } catch (error) {
      this.setData({ loading: false, errorMessage: (error as Error).message });
    }
  }
});
