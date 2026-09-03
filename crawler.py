"""网页内容抓取与提取 (Playwright 无头浏览器版本)"""

import hashlib
import logging
import os
import re
from typing import Optional, Tuple
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

logger = logging.getLogger("webseek")


def fetch_and_extract(
    url: str,
    selector: Optional[str] = None,
    remove_selectors: Optional[list] = None,
    timeout: int = 60,
) -> Tuple[str, str, int]:
    """使用 Playwright 无头浏览器抓取金山文档/普通网页，并提取指定内容。

    返回: (提取的纯文本, SHA-256 哈希, 内容字符数)
    """
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
        page.goto(url, wait_until="networkidle", timeout=timeout * 1000)
        
        # 针对金山多维表格，休眠等待 WebSocket 建立及数据渲染完成
        page.wait_for_timeout(6000)

        # 提取页面可见纯文本及 HTML
        raw_text = page.evaluate("() => document.body ? document.body.innerText : ''")
        page_html = page.content()
        browser.close()

    if not raw_text and not page_html:
        raise ValueError("页面内容加载为空")

    soup = BeautifulSoup(page_html, "lxml")

    # 移除噪音标签
    default_removes = ["script", "style", "nav", "footer"]
    if remove_selectors:
        default_removes.extend(remove_selectors)
    for sel in default_removes:
        for tag in soup.select(sel):
            tag.decompose()

    # 提取目标内容
    if selector:
        target = soup.select_one(selector)
        if target is None:
            logger.warning(f"未匹配到选择器 '{selector}'，降级提取全文渲染文本")
            text = raw_text
        else:
            text = target.get_text()
    else:
        text = raw_text if raw_text.strip() else soup.get_text()

    # 清理多余空行与空格
    lines = [line.strip() for line in text.splitlines()]
    clean_text = "\n".join(line for line in lines if line)

    content_hash = hashlib.sha256(clean_text.encode("utf-8")).hexdigest()
    return clean_text, content_hash, len(clean_text)
