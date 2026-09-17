# -*- coding: utf-8 -*-
"""CSV / TSV 导入（供网页与命令行共用）：把采集/整理的岗位清单写入库。

支持：逗号 CSV、制表符 TSV（Excel / 飞书表格复制粘贴就是 TSV）、带 BOM、CRLF。
"""
import csv
import hashlib
import io
import re

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
    # 飞书/钉钉多维表格导出的列名会带后缀（"岗位链接""投递入口""原链接"…），
    # 这里补全常见写法；仍认不出的交给下面的"包含匹配"兜底。
    "link": ["链接", "投递链接", "报名链接", "官网链接", "url", "link", "申请链接",
             "报名网址", "详情链接", "原文链接", "投递网址", "岗位链接", "职位链接",
             "投递入口", "报名入口", "网申链接", "公告链接", "招聘链接", "投递地址"],
    "deadline": ["截止", "截止时间", "截止日期", "deadline", "报名截止", "报名截止时间",
                 "报名时间", "结束时间", "有效期", "投递截止", "投递截止时间", "截止投递",
                 "报名截止日期", "截止日期时间"],
    "description": ["描述", "要求", "岗位要求", "description", "任职要求", "岗位职责"],
    "job_type": ["岗位类型", "类型", "招聘类型", "job_type", "岗位类别", "招聘类别"],
    "batch": ["届别", "毕业届", "招聘届别", "batch", "毕业年份", "面向届别", "届",
              "招聘批次", "批次", "年份", "面向届次"],
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


def _first_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line
    return ""


# 无表头时的内容猜测用得到
_CITY_WORDS = {"昆明", "大理", "云南", "曲靖", "玉溪", "红河", "楚雄", "昭通", "丽江", "普洱",
               "保山", "临沧", "文山", "西双版纳", "迪庆", "怒江", "德宏",
               "北京", "上海", "广州", "深圳", "成都", "重庆", "杭州", "武汉", "西安", "南京"}
_DEGREE_WORDS = {"本科", "硕士", "博士", "大专", "专科", "不限", "高中", "本科及以上", "硕士研究生"}
# 「云南中烟工业」这种名字里一个上面的关键字都没有（"工业"原先没列），
# 导致无表头复制时公司列猜不出来、岗位名占了第 1 列 —— 补上常见单位后缀。
# 注意别加「工程」：会被「电气工程师」这种岗位名撞上。
_COMPANY_HINT = re.compile(
    r"(公司|集团|局|厂|中心|银行|研究院|研究所|大学|学院|医院|机场|电网|烟草|"
    r"工业|有限|股份|责任|控股|电力|能源|通信|科技|矿业|钢铁|化工|铁路|航空|船舶|"
    r"设计院|勘测|监理|物流|传媒|出版|报社|事务所)")
_URL_RE = re.compile(r"^https?://\S+$", re.I)
_DATE_CELL_RE = re.compile(r"20\d{2}[-/.年]\d{1,2}([-/.月]\d{1,2})?日?$")


def _norm_cell(s) -> str:
    """单元格归一化：飞书/Excel 复制出来的常带全角空格、不间断空格、零宽字符。"""
    return (str(s or "")
            .replace("\u3000", " ").replace("\xa0", " ").replace("\u200b", "")
            .strip())


def _guess_by_content(row) -> dict:
    """**没有表头时**按单元格内容猜列（飞书里只选中数据行复制，就会没有表头）。

    猜法：网址 → 链接；日期格式 → 截止；城市名 → 城市；学历词 → 学历；
    含「公司/集团/局/厂/中心…」→ 公司；剩下第一个够长的文本 → 岗位名。
    """
    mp = {}
    for i, c in enumerate(row):
        c = _norm_cell(c)
        if not c:
            continue
        if "link" not in mp and _URL_RE.match(c):
            mp["link"] = i
        elif "deadline" not in mp and _DATE_CELL_RE.match(c):
            mp["deadline"] = i
        elif "city" not in mp and c in _CITY_WORDS:
            mp["city"] = i
        elif "degree" not in mp and c in _DEGREE_WORDS:
            mp["degree"] = i
        elif "company" not in mp and _COMPANY_HINT.search(c):
            mp["company"] = i
    for i, c in enumerate(row):
        if i in mp.values():
            continue
        cell = _norm_cell(c)
        # 「2026/09/16」这种日期别再当岗位名了（飞书岗位表第一列常常就是"更新日期"）
        if len(cell) >= 3 and not _DATE_CELL_RE.match(cell) and not _URL_RE.match(cell):
            mp["title"] = i
            break
    return mp


def _looks_like_header(row) -> bool:
    """这一行看起来是表头吗？——识别出 ≥2 个字段，或本身就是已知列名。"""
    mp = _detect(row)
    if len(mp) >= 2:
        return True
    for c in row:
        c = _norm_cell(c)
        if not c or len(c) > 8:
            continue
        for aliases in HEADER_ALIAS.values():
            if c in [a.lower() for a in aliases]:
                return True
    return False


def _sniff_delimiter(text: str) -> str:
    """自动认分隔符：逗号 CSV / 制表符 TSV（从 Excel、飞书表格复制粘贴就是 TSV）/ 分号。

    这样"飞书表格里 Ctrl+C → 粘进来"也能直接入库，不需要导出权限。
    """
    head = _first_line(text)
    if not head.strip():
        return ","
    # 引号包起来的字段里出现的分隔符不算
    stripped = re.sub(r'"[^"]*"', '""', head)
    counts = {d: stripped.count(d) for d in ("\t", ",", ";", "|")}
    best = max(counts, key=lambda d: counts[d])
    return best if counts[best] > 0 else ","


def import_csv_text(text: str, source: str = "CSV导入") -> dict:
    """把 CSV / TSV 文本导入数据库，返回统计信息。

    支持：带 BOM、CRLF、逗号或制表符分隔、开头有空行、表头写中文别名。
    """
    text = (text or "").replace("\ufeff", "")
    delim = _sniff_delimiter(text)
    empty = {"rows": 0, "inserted": 0, "updated": 0, "skipped_dup": 0, "flagged": 0,
             "mapping": {}, "delimiter": delim, "warnings": []}
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    if not rows:
        return dict(empty)
    while rows and not any(str(c).strip() for c in rows[0]):
        rows.pop(0)                      # 跳过开头的空行
    if not rows:
        return dict(empty)
    mp = _detect(rows[0])
    warnings = []
    data_start = 1
    no_header = False
    if not _looks_like_header(rows[0]):
        # 没复制表头（飞书里只框选了数据行）→ 第一行也是数据，按内容猜列，别把它吃掉
        guessed = _guess_by_content(rows[0])
        if guessed:
            mp = guessed
            data_start = 0
            no_header = True
            warnings.append("没识别到表头，已按内容自动猜列（"
                            + "、".join(f"{k}={str(rows[0][v]).strip()[:12]}"
                                       for k, v in sorted(mp.items(), key=lambda x: x[1]))
                            + "）；第一行也按数据导入了")
    if "title" not in mp:
        # 兜底：没识别出"岗位"列就用第一列，总比整份文件丢掉强
        mp["title"] = 0
        warnings.append(
            f"未识别到岗位列，已用第一列「{str(rows[0][0]).strip()}」当岗位名")
    jobs = []
    for row in rows[data_start:]:
        if not row or not any(str(c).strip() for c in row):
            continue

        def g(field):
            i = mp.get(field)
            return _norm_cell(row[i]) if (i is not None and i < len(row)) else ""

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
    # 链接列有值但不是网址 → 多半是飞书「超链接」字段复制出来变成了显示文字
    if jobs and "link" in mp and not any(str(j["link"]).lower().startswith("http") for j in jobs):
        warnings.append("链接列有内容但不是网址（飞书/钉钉的「超链接」字段复制出来常是显示文字），"
                        "可回到表格里点开该列改成「URL」字段类型再复制")
    res = db.upsert_jobs(jobs)
    if not jobs and warnings:
        res = {**res, "warnings": warnings}
    return {"rows": len(jobs), **res, "mapping": mp,
            "warnings": warnings, "delimiter": delim}
