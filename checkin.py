#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
2026 GLaDOS 自动签到 (积分增强版)

功能：
- 全自动签到
- 精准获取当前积分 (Points)
- 微信测试号模板消息推送（包含积分、剩余天数、签到结果）
- 智能多域名切换 (优先 glados.cloud)
- 支持 Cookie-Editor 导出格式
"""

import requests
import json
import os
import sys
import time
from datetime import datetime

# Fix Windows Unicode Output
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

# ================= 微信测试号配置（替换成你的！） =================
WECHAT_APPID = os.environ.get("WECHAT_APPID", "")          # 你的测试号appID
WECHAT_APPSECRET = os.environ.get("WECHAT_APPSECRET", "")  # 你的测试号appsecret
WECHAT_TEMPLATE_ID = os.environ.get("WECHAT_TEMPLATE_ID", "")  # 你的模板ID
WECHAT_OPENID = os.environ.get("WECHAT_OPENID", "")        # 你的微信openID

print(f"获取WECHAT_APPID: {WECHAT_APPID}")
print(f"获取WECHAT_APPSECRET: {WECHAT_APPSECRET}")
print(f"获取WECHAT_TEMPLATE_ID: {WECHAT_TEMPLATE_ID}")
print(f"获取WECHAT_OPENID: {WECHAT_OPENID}")

# ================= 原有配置（无需修改） =================
DOMAINS = [
    "https://glados.cloud",
    "https://glados.rocks", 
    "https://glados.network",
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Content-Type': 'application/json;charset=UTF-8',
    'Accept': 'application/json, text/plain, */*',
}

# ================= 工具函数 =================

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")

def extract_cookie(raw: str):
    """提取 Cookie，支持 Cookie-Editor 冒号格式"""
    if not raw: return None
    raw = raw.strip()
    
    # Cookie-Editor 格式 (koa:sess=xxx; koa:sess.sig=yyy)
    if 'koa:sess=' in raw or 'koa:sess.sig=' in raw:
        return raw
        
    # JSON
    if raw.startswith('{'):
        try:
            return 'koa.sess=' + json.loads(raw).get('token')
        except: pass
        
    # JWT Token
    if raw.count('.') == 2 and '=' not in raw and len(raw) > 50:
        return 'koa:sess=' + raw
        
    # Standard
    return raw

def get_cookies():
    raw = os.environ.get("GLADOS_COOKIE", "")
    if not raw:
        log("❌ 未配置 GLADOS_COOKIE")
        return []
    
    # 如果包含账号分隔符 '#'，则支持多账号；否则视为单账号
    # 建议多账号在 Secret 中用 # 隔开，或者直接粘贴原始格式
    accounts = []
    if "#" in raw:
        accounts = [c.strip() for c in raw.split("#") if c.strip()]
    elif "koa:sess" in raw:
        # 针对你这种直接粘贴的情况：将所有行合并为一个 cookie 字符串
        # 移除多余换行，确保 koa:sess 和 koa:sess.sig 在一起
        clean_cookie = raw.replace('\n', '; ').replace('\r', '').strip()
        # 处理可能出现的重复分号
        while ';;' in clean_cookie:
            clean_cookie = clean_cookie.replace(';;', ';')
        accounts = [clean_cookie]
    
    log(f"解析到 cookies 数量: {len(accounts)}")
    return accounts

# ================= 微信测试号推送函数 =================
def get_wechat_access_token():
    """获取微信测试号access_token（有效期2小时）"""
    if not WECHAT_APPID or not WECHAT_APPSECRET:
        log("❌ 微信测试号参数未配置")
        return None
    try:
        url = f"https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid={WECHAT_APPID}&secret={WECHAT_APPSECRET}"
        resp = requests.get(url, timeout=10)
        result = resp.json()
        if "access_token" in result:
            return result["access_token"]
        else:
            log(f"❌ 获取access_token失败: {result}")
            return None
    except Exception as e:
        log(f"❌ 获取access_token异常: {str(e)}")
        return None

def wechat_template_push(title, content_list):
    """微信测试号模板消息推送
    content_list: 传入一个包含各用户信息的列表
    """
    access_token = get_wechat_access_token()
    if not access_token:
        return
    
    # 构造 keyword3 的简洁文本
    content_text = "\n".join(content_list)
    
    url = f"https://api.weixin.qq.com/cgi-bin/message/template/send?access_token={access_token}"
    data = {
        "touser": WECHAT_OPENID,
        "template_id": WECHAT_TEMPLATE_ID,
        "data": {
            "first": {"value": title, "color": "#173177"},
            "keyword1": {"value": f"{title.split('成功')[1]}" if "成功" in title else "签到完成", "color": "#27ae60"},
            "keyword2": {"value": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "color": "#1E90FF"},
            "keyword3": {"value": content_text, "color": "#333333"},
            "remark": {"value": "GLaDOS自动签到通知", "color": "#888888"}
        }
    }
    
    try:
        resp = requests.post(url, json=data, timeout=10)
        result = resp.json()
        if result.get("errcode") == 0:
            log("✅ 微信测试号推送成功")
        else:
            log(f"❌ 微信测试号推送失败: {result.get('errmsg')}")
    except Exception as e:
        log(f"❌ 微信测试号推送异常: {str(e)}")
    
    # 4. 发送推送
    try:
        resp = requests.post(
            url,
            data=json.dumps(data, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json;charset=utf-8"},
            timeout=10
        )
        result = resp.json()
        if result.get("errcode") == 0:
            log("✅ 微信测试号推送成功")
        else:
            log(f"❌ 微信测试号推送失败: {result.get('errmsg')}")
    except Exception as e:
        log(f"❌ 微信测试号推送异常: {str(e)}")

# ================= 核心逻辑（无需修改） =================

class GLaDOS:
    def __init__(self, cookie):
        self.cookie = cookie
        self.domain = DOMAINS[0]
        self.email = "?"
        self.left_days = "?"
        self.points = "?"
        self.points_change = "?"
        self.exchange_info = ""
        self.plan = "?"
        
    def req(self, method, path, data=None):
        """带自动域名切换的请求"""
        for d in DOMAINS:
            try:
                url = f"{d}{path}"
                h = HEADERS.copy()
                h['Cookie'] = self.cookie
                h['Origin'] = d
                h['Referer'] = f"{d}/console/checkin"
                
                if method == 'GET':
                    resp = requests.get(url, headers=h, timeout=10)
                else:
                    resp = requests.post(url, headers=h, json=data, timeout=10)
                
                if resp.status_code == 200:
                    self.domain = d # Remember working domain
                    return resp.json()
            except Exception as e:
                log(f"⚠️ {d} 请求失败: {e}")
                continue
        return None

    def get_status(self):
        """获取状态：天数、邮箱"""
        res = self.req('GET', '/api/user/status')
        if res and 'data' in res:
            d = res['data']
            self.email = d.get('email', 'Unknown')
            self.left_days = str(d.get('leftDays', '?')).split('.')[0]
            return True
        return False

    def get_points(self):
        """获取积分、变化历史、兑换计划"""
        res = self.req('GET', '/api/user/points')
        if res and 'points' in res:
            # 当前积分
            self.points = str(res.get('points', '0')).split('.')[0]
            
            # 最近一次积分变化
            history = res.get('history', [])
            if history:
                last = history[0]
                change = str(last.get('change', '0')).split('.')[0]
                if not change.startswith('-'):
                    change = '+' + change
                self.points_change = change
            
            # 兑换计划
            plans = res.get('plans', {})
            pts = int(self.points)
            exchange_lines = []
            for plan_id, plan_data in plans.items():
                need = plan_data['points']
                days = plan_data['days']
                if pts >= need:
                    exchange_lines.append(f"✅ {need}分→{days}天 (可兑换)")
                else:
                    exchange_lines.append(f"❌ {need}分→{days}天 (差{need-pts}分)")
            self.exchange_info = "<br>".join(exchange_lines)
            return True
        return False

    def checkin(self):
        """执行签到"""
        return self.req('POST', '/api/user/checkin', {'token': 'glados.cloud'})

# ================= 主程序（仅修改推送调用） =================

def main():
    log("🚀 2026 GLaDOS Checkin Starting...")
    cookies = get_cookies()
    if not cookies: sys.exit(1)
    
    push_lines = []  # 用于微信推送的简洁文本列表
    success_cnt = 0
    
    for i, cookie in enumerate(cookies, 1):
        g = GLaDOS(cookie)
        
        # 1. 执行签到
        res = g.checkin()
        msg = res.get('message', 'Failure') if res else "Network Error"
        
        # 2. 获取最新状态
        g.get_status()
        g.get_points()
        
        # 3. 打印日志
        log(f"用户: {g.email} | 积分: {g.points} | 天数: {g.left_days} | 结果: {msg}")
        
        # 4. 构造微信显示的行格式（对应你图片中的样式）
        line = f"用户: {g.email} | 积分: {g.points} | 天数: {g.left_days} | 结果: {msg}"
        push_lines.append(line)
        
        if res and ("Checkin" in msg or "Success" in msg or "tomorrow" in msg):
            success_cnt += 1

    # 5. 执行推送
    if WECHAT_APPID and WECHAT_APPSECRET and WECHAT_TEMPLATE_ID and WECHAT_OPENID:
        title = f"GLaDOS签到: 成功{success_cnt}/{len(cookies)}"
        wechat_template_push(title, push_lines)
    else:
        log("❌ 微信测试号参数未配置完整，跳过推送")

if __name__ == '__main__':
    main()
