#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
GLaDOS 自动签到
- 支持单账号 / 多账号
- 自动切换 GLaDOS 域名
- 签到失败自动重试一次
- 获取积分、剩余天数
- 微信测试号模板消息通知
- 不在日志中输出 Cookie / Secret
"""

import json
import os
import re
import sys
import time
from datetime import datetime

import requests


if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding="utf-8")


# ================= 配置 =================

DOMAINS = [
    "https://glados.cloud",
    "https://glados.rocks",
    "https://glados.network",
]

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

HEADERS = {
    "Content-Type": "application/json;charset=UTF-8",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
}

WECHAT_APPID = os.environ.get("WECHAT_APPID", "")
WECHAT_APPSECRET = os.environ.get("WECHAT_APPSECRET", "")
WECHAT_TEMPLATE_ID = os.environ.get("WECHAT_TEMPLATE_ID", "")
WECHAT_OPENID = os.environ.get("WECHAT_OPENID", "")

NORMAL_CHECKIN_MESSAGES = (
    "checkin! got",
    "checkin repeats",
    "today's observation logged",
)

CURRENT_SESSION_COOKIES = ("gld:sess", "gld:sess.sig")
LEGACY_SESSION_COOKIES = ("koa:sess", "koa:sess.sig")


# ================= 工具函数 =================

def log(message):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {message}")


def mask_email(email):
    """日志中简单隐藏邮箱用户名。"""
    if not email or "@" not in email:
        return "Unknown"

    name, domain = email.split("@", 1)

    if len(name) <= 1:
        masked = "*"
    else:
        masked = name[0] + "***"

    return f"{masked}@{domain}"


def normalize_cookie(value):
    """标准化 Cookie。"""
    if not value:
        return None

    if isinstance(value, dict):
        cookie = value.get("cookie")
        if cookie:
            return normalize_cookie(cookie)

        token = value.get("token")
        if token:
            return f"koa:sess={token}"

        return None

    value = str(value).strip()

    if not value:
        return None

    # 兼容从浏览器请求头直接复制的 `Cookie: ...`。
    value = re.sub(r"^cookie\s*:\s*", "", value, flags=re.IGNORECASE)

    # JSON 对象
    if value.startswith("{"):
        try:
            return normalize_cookie(json.loads(value))
        except (json.JSONDecodeError, TypeError):
            return None

    # 标准 GLaDOS Cookie
    if any(
        f"{name}=" in value
        for name in CURRENT_SESSION_COOKIES + LEGACY_SESSION_COOKIES
    ):
        return (
            value.replace("\r", "")
            .replace("\n", "; ")
            .replace(";;", ";")
            .strip()
        )

    # 单独 JWT
    if value.count(".") == 2 and "=" not in value and len(value) > 50:
        return f"koa:sess={value}"

    return value


def get_cookie_names(cookie_header):
    """仅提取 Cookie 名称，绝不把 Cookie 值写入日志。"""
    names = set()

    for item in cookie_header.split(";"):
        name, separator, _ = item.strip().partition("=")
        if separator and name:
            names.add(name)

    return names


def get_session_cookie_kind(cookie_header):
    """识别完整的新版或旧版签名会话 Cookie。"""
    names = get_cookie_names(cookie_header)

    if set(CURRENT_SESSION_COOKIES).issubset(names):
        return "gld"

    if set(LEGACY_SESSION_COOKIES).issubset(names):
        return "koa"

    return None


def get_browser_headers(user_agent=None):
    """构造与生成当前登录会话的浏览器一致的请求头。"""
    user_agent = (
        (user_agent or "").strip()
        or os.environ.get("GLADOS_USER_AGENT", "").strip()
        or DEFAULT_USER_AGENT
    )
    headers = {"User-Agent": user_agent}

    chrome = re.search(r"(?:Chrome|Chromium)/(\d+)", user_agent)
    if chrome:
        major = chrome.group(1)

        if "Macintosh" in user_agent:
            platform = "macOS"
        elif "Windows" in user_agent:
            platform = "Windows"
        elif "Android" in user_agent:
            platform = "Android"
        elif "Linux" in user_agent:
            platform = "Linux"
        else:
            platform = "Unknown"

        headers.update({
            "Sec-CH-UA": (
                f'"Chromium";v="{major}", '
                f'"Google Chrome";v="{major}", '
                '"Not_A Brand";v="99"'
            ),
            "Sec-CH-UA-Mobile": "?1" if "Mobile" in user_agent else "?0",
            "Sec-CH-UA-Platform": f'"{platform}"',
        })

    return headers


def get_cookies():
    raw = os.environ.get("GLADOS_COOKIE", "").strip()

    if not raw:
        log("❌ 未配置 GLADOS_COOKIE")
        return []

    accounts = []

    # 推荐格式：JSON 数组
    if raw.startswith("["):
        try:
            values = json.loads(raw)

            if isinstance(values, list):
                for value in values:
                    cookie = normalize_cookie(value)
                    if cookie:
                        accounts.append(cookie)

        except json.JSONDecodeError:
            log("⚠️ GLADOS_COOKIE JSON 解析失败")

    # 兼容原来使用 # 分隔多账号的方式
    elif "#" in raw:
        for value in raw.split("#"):
            cookie = normalize_cookie(value)
            if cookie:
                accounts.append(cookie)

    else:
        cookie = normalize_cookie(raw)
        if cookie:
            accounts.append(cookie)

    log(f"✅ 解析到 {len(accounts)} 个 GLaDOS 账号")

    return accounts


def get_accounts():
    """优先读取独立账号；空映射不启用新模式，保留旧配置兼容。"""
    prefix = "GLADOS_COOKIE_"
    account_ids = sorted(
        key[len(prefix):]
        for key, value in os.environ.items()
        if key.startswith(prefix) and value.strip()
    )

    if not account_ids:
        return [
            {"id": f"LEGACY_{index}", "name": f"旧账号{index}",
             "cookie": cookie, "user_agent": None}
            for index, cookie in enumerate(get_cookies(), 1)
        ]

    accounts = []
    for account_id in account_ids:
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", account_id):
            raise ValueError("独立账号标识必须以大写字母开头，仅包含大写字母、数字和下划线")
        raw_cookie = os.environ[prefix + account_id].strip()
        if raw_cookie.startswith("[") or "#" in raw_cookie:
            raise ValueError(f"账号 [{account_id}] 必须只配置一个完整 Cookie")
        cookie = normalize_cookie(raw_cookie)
        if not cookie:
            raise ValueError(f"账号 [{account_id}] 的 Cookie 配置无法解析")
        name = os.environ.get(f"GLADOS_NAME_{account_id}", "").strip() or account_id
        accounts.append({
            "id": account_id,
            "name": name,
            "cookie": cookie,
            "user_agent": os.environ.get(f"GLADOS_USER_AGENT_{account_id}", ""),
        })

    log(f"✅ 读取到 {len(accounts)} 个独立 GLaDOS 账号")
    if os.environ.get("GLADOS_COOKIE", "").strip():
        log("ℹ️ 已启用独立账号配置，旧 GLADOS_COOKIE 不参与本次签到")
    return accounts


def account_label(account):
    return f"{account['name']} [{account['id']}]"


def is_normal_checkin_result(result):
    """成功签到和已经签到过都视为正常。"""
    if not isinstance(result, dict):
        return False

    message = str(result.get("message", "")).strip().lower()

    if any(text in message for text in NORMAL_CHECKIN_MESSAGES):
        return True

    # GLaDOS 历史 API 中 code=0 一般表示成功
    return result.get("code") == 0


# ================= 微信通知 =================

def get_wechat_access_token():
    if not WECHAT_APPID or not WECHAT_APPSECRET:
        return None

    try:
        response = requests.get(
            "https://api.weixin.qq.com/cgi-bin/token",
            params={
                "grant_type": "client_credential",
                "appid": WECHAT_APPID,
                "secret": WECHAT_APPSECRET,
            },
            timeout=10,
        )

        result = response.json()

        token = result.get("access_token")

        if token:
            return token

        log(
            "❌ 获取微信 access_token 失败："
            f"{result.get('errcode')} {result.get('errmsg')}"
        )

    except Exception as exc:
        log(f"❌ 获取微信 access_token 异常：{exc}")

    return None


def wechat_push(success_count, total_count, account_results):
    if not all([
        WECHAT_APPID,
        WECHAT_APPSECRET,
        WECHAT_TEMPLATE_ID,
        WECHAT_OPENID,
    ]):
        log("⚠️ 微信测试号参数未配置完整，跳过微信通知")
        return False

    access_token = get_wechat_access_token()

    if not access_token:
        return False

    all_ok = success_count == total_count

    stats = []

    for item in account_results:
        stats.append(
            f"{item['label']}："
            f"{'正常' if item['success'] else '失败'} / "
            f"{item['points']}积分 / {item['days']}天"
        )

    stats_text = "；".join(stats)

    # 防止多账号时模板字段过长
    if len(stats_text) > 180:
        stats_text = stats_text[:180] + "..."

    title = f"GLaDOS 签到：正常 {success_count}/{total_count}"

    data = {
        "touser": WECHAT_OPENID,
        "template_id": WECHAT_TEMPLATE_ID,
        "data": {
            "first": {
                "value": title,
                "color": "#173177",
            },
            "keyword1": {
                "value": f"正常 {success_count}/{total_count}",
                "color": "#27ae60" if all_ok else "#e74c3c",
            },
            "keyword2": {
                "value": stats_text,
                "color": "#1E90FF",
            },
            "keyword3": {
                "value": "全部正常" if all_ok else "存在失败，请查看 Actions",
                "color": "#333333",
            },
            "remark": {
                "value": "GLaDOS 自动签到通知",
                "color": "#888888",
            },
        },
    }

    try:
        response = requests.post(
            "https://api.weixin.qq.com/cgi-bin/message/template/send",
            params={"access_token": access_token},
            json=data,
            timeout=10,
        )

        result = response.json()

        if result.get("errcode") == 0:
            log("✅ 微信测试号通知发送成功")
            return True

        log(
            "❌ 微信测试号通知失败："
            f"{result.get('errcode')} {result.get('errmsg')}"
        )

    except Exception as exc:
        log(f"❌ 微信测试号通知异常：{exc}")

    return False


# ================= GLaDOS =================

class GLaDOS:
    def __init__(self, cookie, user_agent=None):
        self.cookie = cookie
        self.user_agent = user_agent
        self.domain = DOMAINS[0]
        self.email = "Unknown"
        self.left_days = "?"
        self.points = "?"

        if get_session_cookie_kind(cookie) != "gld":
            log(
                "⚠️ Cookie 未包含完整的 gld:sess 与 gld:sess.sig；"
                "2026-09 新版接口可能返回‘没有权限’"
            )

    def request(self, method, path, data=None):
        for domain in DOMAINS:
            try:
                headers = HEADERS.copy()
                headers.update(get_browser_headers(self.user_agent))
                headers["Cookie"] = self.cookie
                headers["Origin"] = domain
                headers["Referer"] = f"{domain}/console/checkin"

                payload = data

                # 签到 token 与当前尝试的域名保持一致
                if path == "/api/user/checkin":
                    payload = {
                        "token": domain.split("://", 1)[1]
                    }

                url = f"{domain}{path}"

                if method == "GET":
                    response = requests.get(
                        url,
                        headers=headers,
                        timeout=10,
                    )
                else:
                    response = requests.post(
                        url,
                        headers=headers,
                        json=payload,
                        timeout=10,
                    )

                if response.status_code == 200:
                    self.domain = domain
                    return response.json()

                log(
                    f"⚠️ {domain} 返回 HTTP "
                    f"{response.status_code}"
                )

            except Exception as exc:
                log(f"⚠️ {domain} 请求异常：{exc}")

        return None

    def checkin(self):
        return self.request(
            "POST",
            "/api/user/checkin",
        )

    def get_status(self):
        result = self.request(
            "GET",
            "/api/user/status",
        )

        if result and isinstance(result.get("data"), dict):
            data = result["data"]

            self.email = data.get("email", "Unknown")

            days = data.get("leftDays", "?")
            self.left_days = str(days).split(".")[0]

            return True

        return False

    def get_points(self):
        result = self.request(
            "GET",
            "/api/user/points",
        )

        if result and "points" in result:
            self.points = str(
                result.get("points", "?")
            ).split(".")[0]

            return True

        return False


# ================= 主程序 =================

def main():
    log("🚀 GLaDOS Checkin Starting")

    try:
        accounts = get_accounts()
    except ValueError as exc:
        log(f"❌ {exc}")
        return 1

    if not accounts:
        return 1

    success_count = 0
    account_results = []

    for index, account in enumerate(accounts, 1):
        label = account_label(account)
        log(f"========== {label} ==========")

        glados = GLaDOS(account['cookie'], account['user_agent'])

        result = None
        normal = False

        # 第一次失败后等待 60 秒再尝试一次
        for attempt in range(1, 3):
            result = glados.checkin()

            if is_normal_checkin_result(result):
                normal = True
                break

            if attempt == 1:
                log("⚠️ 第一次签到异常，60 秒后重试")
                time.sleep(60)

        message = (
            str(result.get("message", "Unknown"))
            if isinstance(result, dict)
            else "Network Error"
        )

        glados.get_status()
        glados.get_points()

        if normal:
            success_count += 1
            icon = "✅"
        else:
            icon = "❌"

        log(
            f"{icon} {label} | 用户: {mask_email(glados.email)}"
            f" | 积分: {glados.points}"
            f" | 剩余: {glados.left_days} 天"
            f" | 结果: {message}"
        )

        account_results.append({
            "index": index,
            "id": account['id'],
            "label": label,
            "points": glados.points,
            "days": glados.left_days,
            "message": message,
            "success": normal,
        })

    log(
        f"📊 本次结果：正常 "
        f"{success_count}/{len(accounts)}"
    )

    log(
        "🔐 微信配置："
        f"APPID={'已配置' if WECHAT_APPID else '未配置'}, "
        f"APPSECRET={'已配置' if WECHAT_APPSECRET else '未配置'}, "
        f"TEMPLATE_ID={'已配置' if WECHAT_TEMPLATE_ID else '未配置'}, "
        f"OPENID={'已配置' if WECHAT_OPENID else '未配置'}"
    )

    wechat_push(
        success_count,
        len(accounts),
        account_results,
    )

    # 只要有账号真正签到失败，就让 Actions 显示失败
    if success_count != len(accounts):
        log("❌ 存在签到失败账号")
        return 1

    log("✅ 全部账号处理正常")
    return 0


if __name__ == "__main__":
    sys.exit(main())

