# -*- coding: utf-8 -*-
"""CSV 导入（供网页与命令行共用）：把采集/整理的岗位清单写入库。"""
import csv
import hashlib
import io

from . import db

HEADER_ALIAS = {
    "title": ["岗位", "岗位名称", "职位", "职位名称", "title"],
    "company": ["公司", "公司名称", "企业", "company", "单位"],
    "city": ["城市", "地区", "地点", "工作地点", "city"],
    "salary": ["薪资", "薪酬", "工资", "salary"],
    "degree": ["学历", "学历要求", "degree"],
    "tags": ["标签", "岗位标签", "tags"],
    "industry": ["行业", "industry"],
    "link": ["链接", "投递链接", "报名链接", "官网链接", "url", "link", "申请链接"],
    "deadline": ["截止", "截止时间", "截止日期", "deadline", "报名截止"],
    "description": ["描述", "要求", "岗位要求", "description"],
    "job_type": ["岗位类型", "类型", "招聘类型", "job_type"],
    "batch": ["届别", "毕业届", "招聘届别", "batch"],
    "source_name": ["来源", "来源渠道", "source"],
}


def _detect(headers):
    low = [str(h).strip().lower() for h in headers]
    mapping = {}
    for field, aliases in HEADER_ALIAS.items():
        for i, h in enumerate(low):
            if h in [a.lower() for a in aliases]:
                mapping[field] = i
                break
    return mapping


def import_csv_text(text: str, source: str = "CSV导入") -> dict:
    """把 CSV 文本导入数据库，返回统计信息。"""
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return {"rows": 0, "inserted": 0, "updated": 0, "flagged": 0, "mapping": {}}
    mp = _detect(rows[0])
    jobs = []
    for row in rows[1:]:
        if not row or not any(str(c).strip() for c in row):
            continue

        def g(field):
            i = mp.get(field)
            return str(row[i]).strip() if (i is not None and i < len(row)) else ""

        title = g("title")
        if not title:
            continue
        link = g("link")
        dedup = hashlib.md5(f"{title}|{g('company')}|{g('city')}|{link}".encode("utf-8")).hexdigest()[:16]
        jobs.append({
            "source": g("source_name") or source,
            "job_id": dedup,
            "title": title,
            "company": g("company"),
            "city": g("city"),
            "salary": g("salary"),
            "salary_min": None, "salary_max": None,
            "degree": g("degree"),
            "duration": "",
            "tags": g("tags"),
            "industry": g("industry"),
            "link": link,
            "deadline": g("deadline"),
            "published_at": "",
            "description": g("description"),
            "job_type": g("job_type") or "秋招",
            "batch": g("batch"),
            "official_url": link,
        })
    res = db.upsert_jobs(jobs)
    return {"rows": len(jobs), **res, "mapping": mp}
