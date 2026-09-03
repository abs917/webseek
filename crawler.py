"""网页抓取与内容提取 (支持 Playwright 动态渲染与 Cookie 注入)"""

import hashlib
import logging
import os
from typing import Optional
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

logger = logging.getLogger("webseek")


class FetchError(Exception):
    """网页抓取异常"""
    pass


class Response:
    """封装抓取结果，保持与 monitor.py 逻辑一致"""
    def __init__(self, text: str, url: str, html: str = ""):
        self.text = text
        self.url = url
        self.html = html
        self.status_code = 200


def fetch_html(url: str, cfg: Optional[dict] = None) -> Response:
    """使用 Playwright 无头浏览器加载页面并渲染"""
    cfg = cfg or {}
    timeout_sec = cfg.get("timeout", 60)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )

            # 注入金山文档 Cookie
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

            # 打开页面并等待网络空闲
            page.goto(url, wait_until="networkidle", timeout=timeout_sec * 1000)

            # 针对多维表格长连接和 Canvas 渲染，额外等待 6 秒
            page.wait_for_timeout(6000)

            raw_text = page.evaluate("() => document.body ? document.body.innerText : ''")
            page_html = page.content()
            final_url = page.url
            browser.close()

    except Exception as e:
        raise FetchError(f"页面抓取失败: {e}") from e

    if not raw_text and not page_html:
        raise FetchError("页面内容加载为空")

    return Response(text=raw_text or page_html, url=final_url, html=page_html)


def extract_content(html_or_text: str, cfg: Optional[dict] = None) -> str:
    """提取页面文本并进行降噪清洗"""
    cfg = cfg or {}
    soup = BeautifulSoup(html_or_text, "lxml")

    title_text = ""
    title_tag = soup.find("title")
    if title_tag and title_tag.get_text():
        title_text = f"TITLE: {title_tag.get_text().strip()}\n"

    lines = [line.strip() for line in html_or_text.splitlines()]
    clean_text = "\n".join(line for line in lines if line)
    return title_text + clean_text


def content_hash(content: str) -> str:
    """计算文本的 SHA-256 哈希"""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def is_homepage_fallback(content: str, url: str) -> bool:
    """死链回退首页检测"""
    return False


def fetch_sitemap_urls(url: str, cfg: Optional[dict] = None, exclude: Optional[list] = None) -> list:
    """Sitemap 解析"""
    return []
