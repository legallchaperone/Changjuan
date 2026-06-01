App({
  onLaunch() {
    this.globalData.accessToken = wx.getStorageSync("access_token") || "";
    this.globalData.refreshToken = wx.getStorageSync("refresh_token") || "";
    this.globalData.userId = wx.getStorageSync("user_id") || "";
  },
  globalData: {
    apiBaseUrl: "https://api.changjuan.com",
    accessToken: "",
    refreshToken: "",
    userId: ""
  }
});
