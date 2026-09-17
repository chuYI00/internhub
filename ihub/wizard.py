# -*- coding: utf-8 -*-
"""导入向导的解析引擎（纯逻辑，不依赖 Streamlit —— 方便单测）。

为什么单独抽一层：飞书那份岗位表是"只读、不能复制、不能导出"的，进来的路有四条
（上传文件 / 复制粘贴 / F12 抓包解码 / 截图 OCR），**但解析、映射、去重只有一套**。
把这层做成纯函数后，四条通道共用，且能用 `tests/test_wizard.py` 无头测。

标准字段（用户列名千奇百怪，全靠映射）：
    公司 / 岗位名称 / 城市 / 投递链接 / 来源 / 报名截止 / 备注
映射不到的列**不丢**，合并进「备注」。
"""
from __future__ import annotations

import csv
import hashlib
import io
import re
import zipfile

from .importer import (_DATE_CELL_RE, _URL_RE, _detect, _guess_by_content, _looks_like_header,
                       _norm_cell, _sniff_delimiter)

# 「2026/09/16」「2026-09-16」「9月16日」这类当不了岗位名
_DATE_ONLY_RE = re.compile(r"^(20\d{2}[-/.年]\d{1,2}([-/.月]\d{1,2})?日?|\d{1,2}[-/月]\d{1,2}日?)$")
# 纯数字/金额/百分比也当不了
_NUM_ONLY_RE = re.compile(r"^[\d\s,.%元万kK+\-]+$")


def name_like(s) -> bool:
    """这个单元格像不像「名字」（岗位名/公司名）——用来兜底挑岗位列。

    飞书岗位表第一列经常是"更新日期"，老逻辑直接取第一列当岗位名，结果整表岗位名全是日期。
    """
    s = _norm_cell(s)
    if not s or len(s) > 40:
        return False
    if _URL_RE.match(s) or _DATE_ONLY_RE.match(s) or _DATE_CELL_RE.match(s) or _NUM_ONLY_RE.match(s):
        return False
    return bool(re.search(r"[A-Za-z\u4e00-\u9fa5]", s))

# (字段 key, 中文名, 是否必填)
STANDARD_FIELDS = [
    ("title", "岗位名称", True),
    ("company", "公司", False),
    ("city", "城市", False),
    ("link", "投递链接", False),
    ("source_name", "来源", False),
    ("deadline", "报名截止", False),
    ("note", "备注", False),
]

# 映射 UI 里「这一列不导入」的取值
SKIP = -1

# 这些标准字段能复用 importer 的表头别名识别
_FROM_IMPORTER = ("title", "company", "city", "link", "source_name", "deadline")


# ══════════════════════════════════════════════════════════════
#  一、解析：文本 / CSV / Excel
# ══════════════════════════════════════════════════════════════

def _col_to_idx(letters: str) -> int:
    """Excel 列标 A/B/C…AA → 0 起下标。"""
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def read_xlsx(data: bytes) -> list:
    """不装 openpyxl 也能读 .xlsx（xlsx 本身就是 zip + xml）。

    只取第一张工作表，够用；数字/日期按原始文本取，不做类型转换。
    """
    import xml.etree.ElementTree as ET
    NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall(f"{NS}si"):
                shared.append("".join(t.text or "" for t in si.iter(f"{NS}t")))
        sheets = [n for n in z.namelist()
                  if re.match(r"xl/worksheets/sheet\d+\.xml$", n)]
        if not sheets:
            return []
        sheet = sorted(sheets, key=lambda n: int(re.search(r"(\d+)", n).group(1)))[0]
        root = ET.fromstring(z.read(sheet))

    rows = []
    for row in root.iter(f"{NS}row"):
        cells = {}
        for c in row.findall(f"{NS}c"):
            ref = c.get("r") or ""
            m = re.match(r"([A-Z]+)", ref)
            idx = _col_to_idx(m.group(1)) if m else len(cells)
            t = c.get("t")
            v = c.find(f"{NS}v")
            if t == "s" and v is not None:
                try:
                    val = shared[int(v.text)]
                except (ValueError, IndexError):
                    val = ""
            elif t == "inlineStr":
                is_ = c.find(f"{NS}is")
                val = "".join(x.text or "" for x in is_.iter(f"{NS}t")) if is_ is not None else ""
            else:
                val = (v.text or "") if v is not None else ""
            cells[idx] = val
        if cells:
            width = max(cells) + 1
            rows.append([cells.get(i, "") for i in range(width)])
    return rows


def parse_text(text: str, source: str = "粘贴导入") -> dict:
    """解析 CSV / TSV 文本 → {"headers", "rows", "has_header", "warnings"}。

    自动认分隔符（逗号 / 制表符 / 分号）；没表头时按内容猜列，第一行也当数据导。
    """
    text = (text or "").replace("\ufeff", "")
    empty = {"headers": [], "rows": [], "has_header": False, "warnings": [],
             "delimiter": ",", "source": source}
    if not text.strip():
        return empty

    delim = _sniff_delimiter(text)
    rows = [r for r in csv.reader(io.StringIO(text), delimiter=delim)]
    while rows and not any(str(c).strip() for c in rows[0]):
        rows.pop(0)
    if not rows:
        return empty

    warnings = []
    has_header = _looks_like_header(rows[0])
    data_start = 1 if has_header else 0
    if has_header:
        headers = [_norm_cell(h) for h in rows[0]]
    else:
        # 没复制表头（飞书里只框选了数据行）→ 按内容猜列，别把第一行吃掉
        width = max(len(r) for r in rows)
        headers = [f"列{i + 1}" for i in range(width)]
        warnings.append("没识别到表头，已按内容自动猜列，第一行也按数据导入")

    body = []
    for r in rows[data_start:]:
        if not r or not any(str(c).strip() for c in r):
            continue
        r = [_norm_cell(c) for c in r] + [""] * (len(headers) - len(r))
        body.append(r[:len(headers)])

    return {"headers": headers, "rows": body, "has_header": has_header,
            "warnings": warnings, "delimiter": delim, "source": source}


def parse_bytes(name: str, data: bytes, source: str = "") -> dict:
    """按扩展名分派：.csv/.txt → 文本；.xlsx → 内置极简 reader。"""
    name = (name or "").lower()
    src = source or ("文件导入：" + (name or "未命名"))
    if name.endswith(".xlsx") or name.endswith(".xlsm"):
        try:
            rows = read_xlsx(data)
        except Exception as e:                      # zip 坏了 / 不是真 xlsx
            return {"headers": [], "rows": [], "has_header": False, "source": src,
                    "warnings": [f"这个 xlsx 读不出来（{type(e).__name__}）；"
                                 f"请在 Excel 里「另存为 CSV」再传"], "delimiter": ","}
        if not rows:
            return {"headers": [], "rows": [], "has_header": False, "source": src,
                    "warnings": ["文件里没有内容"], "delimiter": ","}
        header = rows[0] if _looks_like_header(rows[0]) else None
        if header:
            headers = [_norm_cell(h) for h in header]
            body = rows[1:]
        else:
            width = max(len(r) for r in rows)
            headers = [f"列{i + 1}" for i in range(width)]
            body = rows
        body = [[_norm_cell(c) for c in r] + [""] * (len(headers) - len(r))
                for r in body if any(str(c).strip() for c in r)]
        body = [r[:len(headers)] for r in body]
        return {"headers": headers, "rows": body, "has_header": bool(header),
                "warnings": [] if header else ["没识别到表头，第一行也按数据导入"],
                "delimiter": "xlsx", "source": src}

    for enc in ("utf-8-sig", "gbk", "utf-8"):
        try:
            return parse_text(data.decode(enc), source=src)
        except UnicodeDecodeError:
            continue
    return parse_text(data.decode("utf-8", "ignore"), source=src)


# ══════════════════════════════════════════════════════════════
#  二、映射
# ══════════════════════════════════════════════════════════════

def guess_mapping(headers: list, sample_rows: list = None) -> dict:
    """猜列名 → 标准字段。返回 {field: 列下标}，没猜到的字段不出现在结果里。"""
    mp = {}
    if headers and any(h for h in headers):
        detected = _detect(headers)
        for f in _FROM_IMPORTER:
            if f in detected:
                mp[f] = detected[f]
        # 备注：列名就叫「备注/说明/注释」的那列
        for i, h in enumerate(headers):
            low = str(h).lower()
            if low in ("备注", "说明", "注释", "note", "remark") and i not in mp.values():
                mp["note"] = i
                break
    if "title" not in mp and sample_rows:
        # 连表头都没认出来（飞书只复制了数据行）→ 按内容猜
        guessed = _guess_by_content(sample_rows[0])
        for f in _FROM_IMPORTER:
            if f in guessed:
                mp[f] = guessed[f]
    if "title" not in mp and sample_rows:
        # 还没定下来 → 挑第一个"像名字"的列。
        # 这一步是为「更新日期 | 公司名称 | 企业性质」这类表准备的：
        # 岗位列认不出来时，把公司名当岗位名，也比拿一列日期强。
        for i, c in enumerate(sample_rows[0]):
            if name_like(c):
                mp["title"] = i
                break
    if "title" not in mp and headers:
        mp["title"] = 0                 # 兜底：第一列当岗位名，总比整份丢掉强
    return mp


def build_jobs(headers: list, rows: list, mapping: dict, source: str = "导入向导",
               job_type: str = "秋招", batch: str = "") -> tuple:
    """按映射把行转成待入库的岗位 dict。未映射的列并进「备注」，不丢信息。

    返回 (jobs, skipped行数)
    """
    mapping = {k: v for k, v in (mapping or {}).items() if v is not None and int(v) >= 0}
    used = set(mapping.values())
    extra_cols = [i for i in range(len(headers or [])) if i not in used]

    def cell(row, field):
        i = mapping.get(field)
        return _norm_cell(row[i]) if (i is not None and i < len(row)) else ""

    jobs, skipped = [], 0
    for row in rows or []:
        title = cell(row, "title")
        if not title:
            skipped += 1
            continue

        bits = []
        note = cell(row, "note")
        if note:
            bits.append(note)
        for i in extra_cols:                       # 没映射到的列 → 备注（列名：值）
            v = _norm_cell(row[i]) if i < len(row) else ""
            if v:
                h = (headers[i] if i < len(headers) and headers[i] else f"列{i + 1}")
                bits.append(f"{h}：{v}")
        note_all = "；".join(bits)

        link = cell(row, "link")
        company = cell(row, "company")
        city = cell(row, "city")
        dedup = hashlib.md5(f"{title}|{company}|{city}|{link}".encode("utf-8")).hexdigest()[:16]
        jobs.append({
            "source": cell(row, "source_name") or source,
            "job_id": dedup,
            "title": title,
            "company": company,
            "city": city,
            "salary": "", "salary_min": None, "salary_max": None,
            "degree": "", "duration": "",
            "tags": "", "industry": "",
            "link": link,
            "deadline": cell(row, "deadline"),
            "published_at": "",
            "description": note_all,
            "job_type": job_type,
            "batch": batch,
            "official_url": link,
        })
    return jobs, skipped


def commit(jobs: list) -> dict:
    """写入库（去重逻辑复用 db.upsert_jobs）。"""
    from . import db
    if not jobs:
        return {"rows": 0, "inserted": 0, "updated": 0, "skipped_dup": 0}
    return db.upsert_jobs(jobs)


# ══════════════════════════════════════════════════════════════
#  三、抓包解码通道用的小工具
# ══════════════════════════════════════════════════════════════

def decoded_csv_path() -> str:
    from . import config
    import os
    return os.path.join(config.PROJECT_ROOT, "data", "飞书岗位导出.csv")


def load_decoded_csv(path: str = None) -> dict:
    """读取 `解码飞书表格.py` 产出的 CSV（存在就读，不存在返回空）。"""
    import os
    p = path or decoded_csv_path()
    if not os.path.exists(p):
        return {"ok": False, "path": p, "msg": "还没生成 —— 先按《飞书只读表格导出实操指南.md》"
                                               "跑一遍 `解码飞书表格.py`"}
    try:
        with open(p, "r", encoding="utf-8-sig") as f:
            text = f.read()
    except Exception as e:
        return {"ok": False, "path": p, "msg": f"读不出来：{type(e).__name__}"}
    res = parse_text(text, source="飞书抓包解码")
    res["ok"] = bool(res["rows"])
    res["path"] = p
    return res
