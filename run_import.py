"""CSV 导入：把其他来源（Excel/官网/群文件等）整理好的岗位清单导入库。
用法：python run_import.py 你的文件.csv   （UTF-8；也可用 UTF-8-SIG/BOM）
表头支持：岗位/岗位名称/职位/title 等，公司,城市,薪资,学历,标签,链接/投递链接,截止/截止日期,描述,来源(默认CSV导入)
"""
import argparse
import csv
import hashlib
import os
import sys

from ihub import db


HEADER_ALIAS = {
    "title": ["岗位", "岗位名称", "职位", "职位名称", "title", "岗位名称名称"],
    "company": ["公司", "公司名称", "企业", "company"],
    "city": ["城市", "地区", "地点", "工作地点", "city"],
    "salary": ["薪资", "薪酬", "工资", "salary"],
    "degree": ["学历", "学历要求", "degree"],
    "tags": ["标签", "岗位标签", "tags"],
    "industry": ["行业", "industry"],
    "link": ["链接", "投递链接", "报名链接", "官网链接", "url", "link", "申请链接"],
    "deadline": ["截止", "截止时间", "截止日期", "deadline", "报名截止"],
    "description": ["描述", "要求", "岗位要求", "描述要求", "description"],
}


def detect_header(headers):
    low = [str(h).strip().lower() for h in headers]
    mapping = {}
    for field, aliases in HEADER_ALIAS.items():
        for i, h in enumerate(low):
            if h in [a.lower() for a in aliases]:
                mapping[field] = i
                break
    return mapping


def main():
    ap = argparse.ArgumentParser(description="导入 CSV 岗位清单（其他来源）")
    ap.add_argument("csv", help="CSV 文件路径（UTF-8）")
    ap.add_argument("--source", default="CSV导入", help="标记数据来源")
    args = ap.parse_args()

    if not os.path.exists(args.csv):
        print("找不到文件：", args.csv)
        sys.exit(1)

    db.init_db()
    jobs = []
    with open(args.csv, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        rows = list(reader)
    if not rows:
        print("空文件")
        return
    mp = detect_header(rows[0])
    for row in rows[1:]:
        if not row or not any(c.strip() for c in row):
            continue
        def g(field):
            i = mp.get(field)
            return row[i].strip() if (i is not None and i < len(row)) else ""
        title = g("title")
        if not title:
            continue
        link = g("link")
        dedup = hashlib.md5(f"{title}|{g('company')}|{g('city')}|{link}".encode("utf-8")).hexdigest()[:16]
        jobs.append({
            "source": args.source,
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
        })
    res = db.upsert_jobs(jobs)
    print(f"读取 {len(jobs)} 行 → 新增 {res['inserted']} / 更新 {res['updated']} / 疑似风险 {res['flagged']}")
    print("表头映射：", mp or "（未识别列名，请确认表头：岗位,公司,城市,薪资,学历,标签,链接,截止日期）")


if __name__ == "__main__":
    main()
