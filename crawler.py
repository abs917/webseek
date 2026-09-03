"""网页抓取与内容提取 (支持 Playwright 动态渲染与 Cookie 注入)"""

import hashlib
import logging
import os
import re
from typing import Optional
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

logger = logging.getLogger("webseek")


class FetchError(Exception):
    """网页抓取异常"""
    pass


class Response:
    """封装抓取结果，保持与原 webseek 监控逻辑完全一致"""
    def __init__(self, text: str, html: str = ""):
        self.text = text
        self.html = html
        self.status_code = 200

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()

    @property
    def content_len(self) -> int:
        return len(self.text)


def fetch_html(url: str, cfg: Optional[dict] = None) -> Response:
    """使用 Playwright 无头浏览器加载页面并渲染，适配金山文档与动态网页"""
    cfg = cfg or {}
    timeout_sec = cfg.get("timeout", 60)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )

            # 注入金山文档 Cookie（读取 GitHub Actions Secrets 环境变量）
            cookie_val = os.getenv("KDOCS_COOKIE", "").strip()
            if cookie_val:
                cookies = []
                for item in cookie_val.split(";"):
                    if "=" in item:
                        name, val = item.strip().split("=", 1)
                        cookies.append({
                            "name": name,
                            "value": val,
                            "domain": ".kdocs.cn",
                            "path": "/",
                        })
                if cookies:
                    context.add_cookies(cookies)

            page = context.new_page()
            logger.info(f"正在使用无头浏览器加载: {url}")

            # 加载网页并等待网络空闲
            page.goto(url, wait_until="networkidle", timeout=timeout_sec * 1000)

            # 针对协同文档与多维表格，额外休眠 6 秒等待长连接与 Canvas/DOM 渲染完成
            page.wait_for_timeout(6000)

            raw_text = page.evaluate("() => document.body ? document.body.innerText : ''")
            page_html = page.content()
            browser.close()

    except Exception as e:
        raise FetchError(f"页面抓取失败: {e}") from e

    if not raw_text and not page_html:
        raise FetchError("页面内容加载为空")

    # 根据配置中的选择器进行内容过滤或降噪
    soup = BeautifulSoup(page_html, "lxml")
    default_removes = ["script", "style", "nav", "footer"]
    remove_selectors = cfg.get("remove_selectors") or []
    default_removes.extend(remove_selectors)

    for sel in default_removes:
        for tag in soup.select(sel):
            tag.decompose()

    selector = cfg.get("selector")
    if selector:
        target = soup.select_one(selector)
        if target is None:
            logger.warning(f"未匹配到选择器 '{selector}'，降级提取页面渲染文本")
            text = raw_text
        else:
            text = target.get_text()
    else:
        text = raw_text if raw_text.strip() else soup.get_text()

    # 清除多余空行与两端空格
    lines = [line.strip() for line in text.splitlines()]
    clean_text = "\n".join(line for line in lines if line)

    return Response(text=clean_text, html=page_html)
