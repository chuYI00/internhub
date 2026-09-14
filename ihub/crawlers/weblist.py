# -*- coding: utf-8 -*-
"""声明式多源网页抓取：把"能自动抓"的站点写成配置，一次并行抓完，统一入库。

配置：data/sources.json（数组），每条：
{
  "name": "云南省人社厅·通知公告",       # 数据源名（入库 source 字段）
  "url": "https://hrss.yn.gov.cn/NewsLsit.aspx?ClassID=558",
  "link_regex": "NewsView\\.aspx\\?NewsID=",   # 只取匹配该正则的链接
  "job_type": "秋招",                  # 实习/秋招
  "city": "昆明",                      # 归属城市（站点本身不区分时用）
  "keyword_regex": "招聘|选调|事业单位|国企|校园", # 标题需命中（可空）
  "base": "https://hrss.yn.gov.cn",     # 相对链接补全前缀（可空=自动）
  "enabled": true
}
"""
import hashlib
import json
import os
import re
import time

import requests

from .. import config
from .base import BaseCrawler

SOURCES_PATH = os.path.join(config.DATA_DIR, "sources.json")

TAG_RE = re.compile(r"<[^>]+>")
A_RE = re.compile(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', flags=re.S | re.I)
DATE_RE = re.compile(r"(20\d{2}[-/年.]\d{1,2}[-/月.]\d{1,2})")


def load_sources():
    try:
        with open(SOURCES_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _text(html_fragment):
    return re.sub(r"\s+", " ", TAG_RE.sub("", html_fragment)).strip()


CITY_HINTS = ["潍坊", "济南", "青岛", "烟台", "威海", "昆明", "大理", "曲靖", "玉溪",
              "北京", "上海", "深圳", "广州", "成都", "杭州", "南京", "武汉", "西安", "重庆"]
NOISE_TITLES = ["取消宣讲", "场地变更", "时间变更", "已过期", "查看更多", "首页", "注册", "登录"]


def _clean_title(t: str) -> str:
    t = re.sub(r'^[^0-9A-Za-z\u4e00-\u9fa5]+', '', t or "")      # 去掉开头的引号/尖括号等
    t = re.sub(r'^["\'>\-\s]+', '', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def _is_meaningful(t: str) -> bool:
    if len(t) < 8:
        return False
    if len(re.findall(r"[\u4e00-\u9fa5]", t)) < 4:                 # 至少 4 个汉字
        return False
    if any(n in t for n in NOISE_TITLES):
        return False
    return True


def _guess_city(t: str, fallback: str) -> str:
    for c in CITY_HINTS:
        if c in t:
            return c
    return fallback


class WebListCrawler(BaseCrawler):
    """按配置抓取多个站点的列表页（一次运行覆盖所有启用源）。"""

    name = "网页列表(多源)"

    def fetch_city(self, city, max_pages=1, verbose=True):
        jobs = []
        sources = [s for s in load_sources() if s.get("enabled", True)]
        if not sources:
            if verbose:
                print(f"  [提示] 未配置数据源：请编辑 {SOURCES_PATH}")
            return jobs
        for s in sources:
            url = s.get("url")
            if not url:
                continue
            if verbose:
                print(f"  [源] {s.get('name')} → {url}")
            try:
                r = requests.get(url, headers={"User-Agent": config.USER_AGENT},
                                 timeout=config.TIMEOUT)
                r.encoding = r.apparent_encoding or "utf-8"
                html = r.text
            except Exception as e:
                print(f"    [失败] {e}")
                continue
            items = self._parse(html, s, url)
            if verbose:
                print(f"    解析 {len(items)} 条")
            jobs.extend(items)
            self._throttle()
        return jobs

    def _parse(self, html, s, page_url):
        out = []
        link_re = re.compile(s["link_regex"]) if s.get("link_regex") else None
        kw_re = re.compile(s["keyword_regex"]) if s.get("keyword_regex") else None
        base = s.get("base") or ""
        seen = set()
        for href, inner in A_RE.findall(html):
            title = _clean_title(_text(inner))
            if not _is_meaningful(title):
                continue
            if link_re and not link_re.search(href):
                continue
            if kw_re and not kw_re.search(title):
                continue
            # 相对链接补全
            full = href
            if full.startswith("//"):
                full = "http:" + full
            elif full.startswith("/"):
                if base:
                    full = base.rstrip("/") + full
                else:
                    m = re.match(r"(https?://[^/]+)", page_url)
                    full = (m.group(1) if m else "") + full
            elif not full.startswith("http"):
                full = page_url.rsplit("/", 1)[0] + "/" + full
            if full in seen:
                continue
            seen.add(full)
            # 截止日期（列表页偶有）
            deadline = ""
            m = DATE_RE.search(title)
            if m:
                deadline = m.group(1)
            job_id = hashlib.md5(full.encode("utf-8")).hexdigest()[:16]
            out.append({
                "source": s.get("name") or "网页列表",
                "job_id": job_id,
                "title": title[:120],
                "company": s.get("company") or s.get("name") or "",
                "city": _guess_city(title, s.get("city") or ""),
                "salary": "",
                "salary_min": None, "salary_max": None,
                "degree": "",
                "duration": "",
                "tags": s.get("tags") or "",
                "industry": s.get("industry") or "",
                "link": full,
                "deadline": deadline,
                "published_at": "",
                "official_url": full,
                "job_type": s.get("job_type") or "秋招",
                "batch": s.get("batch") or "2027届",
                "requirement": "",
                "description": s.get("note") or "",
            })
        return out
