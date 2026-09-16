# -*- coding: utf-8 -*-
"""解析"浏览器另存的网页"(Ctrl+S) 里的岗位，入库。

用法：
  1. 浏览器打开岗位列表页（登录状态、滚动加载完）→ Ctrl+S → 只保存 HTML → 存到 导入网页\
  2. 在本目录运行：venv\Scripts\python.exe run_parse_html.py
"""
import glob
import hashlib
import os
import re
import sys

from ihub import config, db

IN_DIR = os.path.join(config.PROJECT_ROOT, "导入网页")
KW = re.compile(r"招聘|校招|宣讲|实习|选调|岗位|人才|双选|需求|工程师|专员|经理|助理")
SKIP = re.compile(r"登录|注册|首页|更多|下一页|上一页|隐私|协议|关于我们|招聘指南|申请表")
ITEM = re.compile(r"(https?://[^\s\"']+|/[^\s\"']*(?:job|position|detail|recruit|career|zpxx|zpinfo|content)[^\s\"']*)", re.I)
TAG = re.compile(r"<[^>]+>")
CITY_HINTS = ["潍坊", "济南", "青岛", "烟台", "威海", "昆明", "大理", "曲靖", "玉溪", "丽江",
              "北京", "上海", "深圳", "广州", "成都", "杭州", "南京", "武汉", "西安", "重庆", "天津", "长沙"]


def parse_html(path: str):
    html = open(path, "r", encoding="utf-8", errors="ignore").read()
    html = re.sub(r"<script.*?</script>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<style.*?</style>", " ", html, flags=re.S | re.I)
    jobs, seen = [], set()
    for href, inner in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, flags=re.S | re.I):
        title = re.sub(r"\s+", " ", TAG.sub("", inner)).strip()
        title = re.sub(r'^[^0-9A-Za-z\u4e00-\u9fa5]+', '', title)
        if len(title) < 6 or len(re.findall(r"[\u4e00-\u9fa5]", title)) < 4:
            continue
        if SKIP.search(title) or not KW.search(title):
            continue
        if not ITEM.search(href):
            continue
        if href.startswith("//"):
            href = "http:" + href
        if href in seen:
            continue
        seen.add(href)
        city = next((c for c in CITY_HINTS if c in title), "")
        jobs.append({
            "source": "网页导入:" + os.path.basename(path)[:28],
            "job_id": hashlib.md5(href.encode("utf-8")).hexdigest()[:16],
            "title": title[:120],
            "company": "",
            "city": city,
            "salary": "", "salary_min": None, "salary_max": None,
            "degree": "", "duration": "", "tags": "", "industry": "",
            "link": href,
            "deadline": "", "published_at": "", "official_url": href,
            "job_type": "秋招", "batch": "2027届",
            "requirement": "", "description": "",
        })
    return jobs


def main():
    db.init_db()
    os.makedirs(IN_DIR, exist_ok=True)
    files = glob.glob(os.path.join(IN_DIR, "*.htm*"))
    if not files:
        print(f"没找到网页文件。请把浏览器保存的 HTML 放到：{IN_DIR}")
        return
    total = 0
    for f in files:
        jobs = parse_html(f)
        res = db.upsert_jobs(jobs)
        total += res["inserted"]
        print(f"{os.path.basename(f)} → 解析 {len(jobs)} 条，新增 {res['inserted']} / 更新 {res['updated']}")
    print(f"\n完成：共新增 {total} 条。刷新网站查看（岗位类型选“秋招”）。")
    print("提示：若链接是相对路径（/detail/xxx），入库后可能点不开；可在浏览器里复制完整地址后手动修正。")


if __name__ == "__main__":
    main()
