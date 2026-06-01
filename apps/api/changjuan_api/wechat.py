from __future__ import annotations

from dataclasses import dataclass

import httpx

from .contracts import WxLoginRequest
from .settings import Settings


@dataclass(frozen=True)
class WechatIdentity:
    openid: str
    unionid: str | None = None


class WechatLoginError(Exception):
    pass


def resolve_wechat_identity(payload: WxLoginRequest, settings: Settings) -> WechatIdentity:
    if payload.wx_openid:
        if settings.app_env == "production":
            raise WechatLoginError("wx_code required for production WeChat login")
        return WechatIdentity(openid=payload.wx_openid, unionid=payload.wx_unionid)

    if not payload.wx_code:
        raise WechatLoginError("wx_code required")

    mapped = settings.wechat_login_code_map.get(payload.wx_code)
    if mapped:
        return WechatIdentity(openid=str(mapped["openid"]), unionid=mapped.get("unionid"))

    if not settings.wechat_app_id or not settings.wechat_app_secret:
        raise WechatLoginError("wechat code exchange is not configured")

    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(
                settings.wechat_code2session_url,
                params={
                    "appid": settings.wechat_app_id,
                    "secret": settings.wechat_app_secret,
                    "js_code": payload.wx_code,
                    "grant_type": "authorization_code",
                },
            )
            response.raise_for_status()
            body = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise WechatLoginError("wechat code exchange failed") from exc

    if body.get("errcode"):
        message = body.get("errmsg") or body["errcode"]
        raise WechatLoginError(f"wechat code exchange failed: {message}")

    openid = body.get("openid")
    if not openid:
        raise WechatLoginError("wechat code exchange returned no openid")

    return WechatIdentity(openid=str(openid), unionid=body.get("unionid"))
