# -*- coding: utf-8 -*-
"""通用 RSS / Atom 订阅源爬虫（可作为任意官方渠道的接入方式）。

用法：在 ihub/config.py 的 RSS_FEEDS 里添加订阅地址，例如：
  RSS_FEEDS = [
      {"url": "https://某校就业网/rss.xml", "name": "某高校就业信息网"},
  ]
本爬虫只读取站点**公开发布的 RSS/Atom**（订阅本就是其提供的能力），不触碰列表页反爬。
若站点不提供 RSS，请改用 CSV 导入（run_import.py）。
"""
import datetime
import xml.etree.ElementTree as ET

import requests

from .. import config
from .base import BaseCrawler


def _ns(tag):
    """去掉命名空间，返回本地名。"""
    return tag.split("}")[-1] if "}" in tag else tag


class RssCrawler(BaseCrawler):
    name = "RSS订阅"

    def fetch_city(self, city, max_pages=1, verbose=True):
        # 订阅源与城市无关，直接抓配置中的所有 feed
        jobs = []
        feeds = getattr(config, "RSS_FEEDS", [])
        if not feeds:
            if verbose:
                print("  [提示] 未配置 RSS_FEEDS，请在 ihub/config.py 中添加订阅地址")
            return jobs
        for feed in feeds:
            url = feed.get("url", "") if isinstance(feed, dict) else ""
            name = feed.get("name", "RSS") if isinstance(feed, dict) else "RSS"
            if not url:
                continue
            if verbose:
                print(f"  [RSS] {name}: {url}")
            try:
                r = requests.get(url, headers={"User-Agent": config.USER_AGENT},
                                 timeout=config.TIMEOUT)
                r.raise_for_status()
                jobs += self._parse(r.content, name)
            except Exception as e:
                print(f"  [RSS失败] {name}: {e}")
        return jobs

    def _parse(self, content, source_name):
        out = []
        try:
            root = ET.fromstring(content)
        except Exception:
            return out
        items = []
        # RSS 2.0: channel/item；Atom: feed/entry
        for child in root.iter():
            if _ns(child.tag) == "item" or _ns(child.tag) == "entry":
                items.append(child)
        for it in items:
            title = link = desc = date = ""
            for c in it.iter():
                t = _ns(c.tag)
                if t in ("title", "link", "description", "pubDate", "published", "updated"):
                    val = (c.text or "").strip()
                    if t == "title":
                        title = val
                    elif t == "link":
                        link = c.get("href") or val
                    elif t in ("description", "pubDate", "published", "updated"):
                        desc = desc or val
                        if t != "description":
                            date = val
            if not title:
                continue
            # 去重 id
            job_id = f"rss-{hash((source_name, title, link)) & 0xffffffff:x}"
            if isinstance(date, str):
                date = date[:10]
            out.append({
                "source": source_name,
                "job_id": job_id,
                "title": title[:120],
                "company": "",
                "city": "",
                "salary": "",
                "salary_min": None,
                "salary_max": None,
                "degree": "",
                "duration": "",
                "tags": "",
                "industry": "",
                "link": link or "",
                "deadline": "",
                "published_at": date or datetime.date.today().isoformat(),
                "official_url": "",
                "requirement": "",
                "description": desc[:500],
            })
        return out
