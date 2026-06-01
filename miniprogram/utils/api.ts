type ApiEnvelope<T> = {
  code: number;
  data: T;
  message: string;
  trace_id: string;
};

const app = getApp<{ globalData: { apiBaseUrl: string; accessToken: string } }>();

export function request<T>(
  path: string,
  method: WechatMiniprogram.RequestOption["method"],
  data?: string | WechatMiniprogram.IAnyObject | ArrayBuffer,
) {
  return new Promise<T>((resolve, reject) => {
    wx.request({
      url: `${app.globalData.apiBaseUrl}${path}`,
      method,
      data,
      header: app.globalData.accessToken
        ? { Authorization: `Bearer ${app.globalData.accessToken}` }
        : {},
      success(response) {
        const body = response.data as ApiEnvelope<T>;
        if (response.statusCode >= 200 && response.statusCode < 300 && body.code === 0) {
          resolve(body.data);
        } else {
          reject(new Error(body.message || "request failed"));
        }
      },
      fail: reject
    });
  });
}
