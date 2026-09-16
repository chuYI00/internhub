# -*- coding: utf-8 -*-
"""CSV 导入（供网页与命令行共用）：把采集/整理的岗位清单写入库。"""
import csv
import hashlib
import io

from . import db

HEADER_ALIAS = {
    "title": ["岗位", "岗位名称", "职位", "职位名称", "title", "招聘岗位", "招聘职位"],
    "company": ["公司", "公司名称", "企业", "company", "单位", "单位名称",
                "用人单位", "招聘单位", "机构", "集团"],
    "city": ["城市", "地区", "地点", "工作地点", "city", "工作城市", "所在城市",
             "工作地区", "省份", "所在地"],
    "salary": ["薪资", "薪酬", "工资", "salary", "薪资待遇", "待遇", "月薪", "年薪"],
    "degree": ["学历", "学历要求", "degree", "最低学历", "学位"],
    "tags": ["标签", "岗位标签", "tags", "备注", "专业", "专业要求", "方向", "类别"],
    "industry": ["行业", "industry"],
    "link": ["链接", "投递链接", "报名链接", "官网链接", "url", "link", "申请链接",
             "报名网址", "详情链接", "原文链接", "投递网址"],
    "deadline": ["截止", "截止时间", "截止日期", "deadline", "报名截止", "报名截止时间",
                 "报名时间", "结束时间", "有效期"],
    "description": ["描述", "要求", "岗位要求", "description", "任职要求", "岗位职责"],
    "job_type": ["岗位类型", "类型", "招聘类型", "job_type", "岗位类别", "招聘类别"],
    "batch": ["届别", "毕业届", "招聘届别", "batch", "毕业年份", "面向届别", "届"],
    "source_name": ["来源", "来源渠道", "source", "数据来源", "平台"],
}

# 包含匹配（"工作城市" 含 "城市"）时字段的优先级：
# 越具体的字段先匹配，避免 "岗位类型" 被当成 "岗位"（title）
_FUZZY_ORDER = ["job_type", "batch", "deadline", "salary", "degree", "company", "city",
                "link", "description", "tags", "industry", "source_name", "title"]


def _norm(h) -> str:
    """表头归一化：去掉 Excel/采集助手写出的 BOM、首尾空格与不可见字符。

    曾经的坑：导出的 CSV 带 UTF-8 BOM 时，第一列会变成 "\\ufeff岗位"，
    跟别名表对不上，于是整份文件被静默跳过（0 条导入）。
    """
    return str(h).replace("\ufeff", "").replace("\u200b", "").strip().lower()


def _detect(headers):
    """识别表头 → 字段下标。

    两步：先精确匹配别名（"岗位"/"公司"），再用"包含"匹配兜住常见变体
    （"单位名称"含"单位"、"工作城市"含"城市"、"报名截止时间"含"截止"）。
    """
    low = [_norm(h) for h in headers]
    mapping = {}
    used = set()

    # 第 1 步：精确
    for field, aliases in HEADER_ALIAS.items():
        for i, h in enumerate(low):
            if h and h in [a.lower() for a in aliases]:
                mapping[field] = i
                used.add(i)
                break

    # 第 2 步：包含（按具体→宽泛的优先级，且不抢已被精确匹配占用的列）
    for field in _FUZZY_ORDER:
        if field in mapping:
            continue
        for alias in HEADER_ALIAS[field]:
            a = alias.lower()
            hit = None
            for i, h in enumerate(low):
                if not h or i in used:
                    continue
                if a in h or h in a:
                    hit = i
                    break
            if hit is not None:
                mapping[field] = hit
                used.add(hit)
                break
    return mapping


def import_csv_text(text: str, source: str = "CSV导入") -> dict:
    """把 CSV 文本导入数据库，返回统计信息。"""
    rows = list(csv.reader(io.StringIO(text.replace("\ufeff", ""))))
    if not rows:
        return {"rows": 0, "inserted": 0, "updated": 0, "flagged": 0, "mapping": {}}
    while rows and not any(str(c).strip() for c in rows[0]):
        rows.pop(0)                      # 跳过开头的空行
    if not rows:
        return {"rows": 0, "inserted": 0, "updated": 0, "flagged": 0, "mapping": {}}
    mp = _detect(rows[0])
    warnings = []
    if "title" not in mp:
        # 兜底：没识别出"岗位"列就用第一列，总比整份文件丢掉强
        mp["title"] = 0
        warnings.append(
            f"未识别到岗位列，已用第一列「{str(rows[0][0]).strip()}」当岗位名")
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
    if not jobs and warnings:
        res = {**res, "warnings": warnings}
    return {"rows": len(jobs), **res, "mapping": mp,
            "warnings": warnings}
