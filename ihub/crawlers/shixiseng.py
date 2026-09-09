"""实习僧爬虫。

解析策略（二选一，自动降级）：
1) 主路径：页面为 Nuxt SSR，内嵌 `window.__NUXT__=...` 的 JS 表达式。
   若本机装有 Node.js，则用 Node 执行该表达式得到 JSON，直接取结构化字段
   （标题/公司/城市/薪资数字/学历/标签等，薪资无图标字体乱码）。
2) 备用路径：无 Node 时用 BeautifulSoup 解析服务端渲染的卡片 DOM，
   标题/链接/城市/公司/标签可用；薪资为图标字体时会显示为原始文本或“面议”。

合规：抓取前检查 robots.txt；每页间隔见 config.REQUEST_DELAY；每城市页数受限；
仅保留原始官方链接（不做任何改写）。
"""
import json
import re
import shutil
import subprocess
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from .. import config
from .base import BaseCrawler

_BASE = "https://www.shixiseng.com"


def _find_nuxt_expr(html: str):
    m = re.search(r"window\.__NUXT__\s*=\s*(.*?)</script>", html, flags=re.S)
    if not m:
        return None
    expr = m.group(1).strip()
    if expr.endswith(";"):
        expr = expr[:-1]
    return expr


def _eval_nuxt(expr: str):
    """用 Node 执行 __NUXT__ 表达式，返回对象或 None。"""
    node = shutil.which("node")
    if not node:
        return None
    js = "console.log(JSON.stringify(" + expr + "));"
    try:
        p = subprocess.run([node, "-e", js], capture_output=True, text=True,
                           timeout=20, encoding="utf-8", errors="replace")
        if p.returncode != 0:
            return None
        return json.loads(p.stdout)
    except Exception:
        return None


def _find_records(html: str):
    """先尝试 Node 解析 NUXT，失败则返回 None（走 DOM）。"""
    expr = _find_nuxt_expr(html)
    if not expr:
        return None, None
    obj = _eval_nuxt(expr)
    if not obj:
        return None, None
    try:
        data = obj["data"][0]["interns"]["data"]
        total = obj["data"][0]["interns"].get("total")
        return data, total
    except Exception:
        return None, None


def _clean(s):
    """清洗标题等文本：去掉 HTML 实体形式的图标字体与私有区字符。"""
    if not s:
        return ""
    s = re.sub(r"&#x[0-9a-fA-F]+;?", "", s)   # &#xe3fe / &#xe3fe; 之类
    s = re.sub(r"[\ue000-\uf8ff]", "", s)     # 私有区图标字
    s = re.sub(r"&#\d+;?", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _fmt_salary(min_sal, max_sal):
    """把薪资数字转展示文本。"""
    try:
        lo = int(min_sal)
        hi = int(max_sal)
    except (TypeError, ValueError):
        return "面议"
    if lo <= 0 and hi <= 0:
        return "面议"
    if lo == hi:
        return f"{lo}元/天" if lo and lo < 1000 else (f"{lo}元/天")
    if lo <= 0:
        return f"最高{hi}元/天"
    if hi <= 0:
        return f"{lo}元/天起"
    return f"{lo}-{hi}元/天"


def _to_job(rec) -> dict:
    job_id = str(rec.get("uuid") or "")
    link = f"{_BASE}/intern/{job_id}" if job_id else ""
    tags = rec.get("i_tags") or []
    name = _clean(rec.get("name"))
    cname = _clean(rec.get("cname"))
    salary = _fmt_salary(rec.get("minsalary"), rec.get("maxsalary"))
    return {
        "source": "实习僧",
        "job_id": job_id,
        "title": name,
        "company": cname,
        "city": _clean(rec.get("city")),
        "salary": salary,
        "salary_min": rec.get("minsalary"),
        "salary_max": rec.get("maxsalary"),
        "degree": _clean(rec.get("degree")),
        "duration": _clean(rec.get("month_num")),
        "tags": "、".join(_clean(t) for t in tags),
        "industry": _clean(rec.get("industry")),
        "link": link,
        "deadline": None,
        "published_at": None,
        "requirement": "",
        "description": "",
    }


def _parse_dom(html: str, default_city: str):
    """备用：DOM 解析卡片（无 Node 时使用）。"""
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for card in soup.select("div.intern-item"):
        a = card.select_one("a[href*='/intern/']")
        if not a:
            continue
        href = a.get("href") or ""
        if href.startswith("/"):
            href = _BASE + href
        title = (a.get("title") or a.get_text(" ", strip=True) or "").strip()
        city_el = card.select_one(".intern-detail__job .city")
        city = (city_el.get_text(strip=True) if city_el else default_city)
        comp_el = card.select_one(".intern-detail__company a.title")
        company = comp_el.get("title") or comp_el.get_text(strip=True) or ""
        tags_el = card.select(".intern-label")
        tags = "、".join(t.get("title") or t.get_text(strip=True) for t in tags_el)
        job_id = card.get("data-intern-id") or ""
        out.append({
            "source": "实习僧",
            "job_id": job_id or (href.split("/intern/")[-1].split("?")[0] if "/intern/" in href else ""),
            "title": title,
            "company": company.strip(),
            "city": city,
            "salary": "面议（原始页面为准）",
            "salary_min": None, "salary_max": None,
            "degree": "", "duration": "", "tags": tags, "industry": "",
            "link": href.split("?")[0],
            "deadline": None, "published_at": None,
            "requirement": "", "description": "",
        })
    return out


class ShixisengCrawler(BaseCrawler):
    name = "实习僧"

    def fetch_city(self, city, max_pages=1, verbose=True):
        jobs = []
        for page in range(1, max_pages + 1):
            url = f"{_BASE}/interns?keyword=&city={quote(city)}&page={page}"
            if not self.check_robots(url):
                break
            if verbose:
                print(f"  page {page}: {url}")
            try:
                r = requests.get(url, headers={"User-Agent": config.USER_AGENT},
                                 timeout=config.TIMEOUT)
                r.raise_for_status()
                r.encoding = "utf-8"
                html = r.text
            except Exception as e:
                print(f"  [请求失败] {e}")
                break
            recs, total = _find_records(html)
            if recs is None:
                page_jobs = _parse_dom(html, city)
                if verbose:
                    print(f"  [备用DOM] 本页 {len(page_jobs)} 条")
            else:
                page_jobs = [_to_job(rr) for rr in recs if rr.get("uuid")]
                if verbose:
                    print(f"  [结构化] 本页 {len(page_jobs)} 条（总计约 {total}）")
            if not page_jobs:
                # 可能被风控或结构变化
                if verbose:
                    print("  [提示] 本页无数据：可能被风控或页面结构变化，请稍后再试")
                break
            jobs.extend(page_jobs)
            if page < max_pages:
                self._throttle()
        return jobs

    def fetch_deadline(self, job_id: str) -> str:
        """进入岗位详情页抓“截止日期”。返回 'YYYY-MM-DD' 或空字符串。"""
        if not job_id:
            return ""
        url = f"{_BASE}/intern/{job_id}"
        if not self.check_robots(url):
            return ""
        try:
            r = requests.get(url, headers={"User-Agent": config.USER_AGENT},
                             timeout=config.TIMEOUT)
            r.raise_for_status()
            r.encoding = "utf-8"
            m = re.search(r"截止日期\s*[：:]\s*(\d{4}-\d{2}-\d{2})", r.text)
            self._throttle()
            return m.group(1) if m else ""
        except Exception:
            return ""

    def enrich_deadlines(self, jobs, cap=20, verbose=True):
        """给前 cap 条抓不到截止时间的岗位补抓详情页截止日期（就地修改 dict）。"""
        done = 0
        for j in jobs:
            if done >= cap:
                break
            if j.get("deadline"):
                continue
            dl = self.fetch_deadline(str(j.get("job_id") or ""))
            if dl:
                j["deadline"] = dl
                done += 1
                if verbose:
                    print(f"  [详情] {j.get('title', '')[:14]} 截止 {dl}")
        return done
