# -*- coding: utf-8 -*-
"""飞书多维表格（Base/Bitable）→ InternHub 岗位库的桥接。

用法分两步：
  1. 在 WorkBuddy 里装/授权「飞书」连接器（按你自己的账号权限读表）；
  2. 连接器把记录读出来（JSON）→ 交给本模块 → 自动进岗位库。

为什么不直接写爬虫：飞书多维表格的数据接口要登录（匿名返回 `Login Required`），
而表格若被所有者设了「禁止复制/下载/打印」，绕过它去批量抓取是不合适的。
走连接器 = 走飞书官方、按授权身份读，权限由飞书自己判定。

设计要点：
  - **不自己重写一遍表头匹配**，而是把记录转成 CSV 文本，交给 `ihub.importer` 那套
    别名识别（招聘单位/招聘岗位/工作城市/投递截止时间/岗位链接/招聘批次…）——避免出现
    "两套实现各改各的"（这个项目已经踩过两次：sources.json 双份、run_import 双份）。
  - 单元格类型很杂（文本/数字/日期(毫秒时间戳)/单选/多选/复选/超链接/人员/附件），
    统一归一化成字符串；超链接要取 URL 而不是显示文字。
"""
import io
import json
import os
import re
from urllib.parse import parse_qs, urlparse

from . import importer

# 单元格里出现的各种"空"表示
_EMPTY = {"", "-", "—", "null", "None", "nan"}


def parse_base_url(url: str) -> dict:
    """从飞书多维表格链接里解出连接器需要的参数。

    例：https://kcnrqqpruo3a.feishu.cn/base/Hmiibiihoav4SXs56Ufc6DkEnxq?table=tblmZUlIlvcSgH3V&view=vew9fn2Zdf
    → {'host': 'kcnrqqpruo3a.feishu.cn', 'app_token': 'Hmiibiihoav4SXs56Ufc6DkEnxq',
       'table_id': 'tblmZUlIlvcSgH3V', 'view_id': 'vew9fn2Zdf'}
    """
    out = {"host": "", "app_token": "", "table_id": "", "view_id": ""}
    if not url:
        return out
    u = urlparse(url.strip())
    out["host"] = u.netloc
    m = re.search(r"/(?:base|wiki)/([A-Za-z0-9]+)", u.path)
    if m:
        out["app_token"] = m.group(1)
    q = parse_qs(u.query)
    out["table_id"] = (q.get("table") or [""])[0]
    out["view_id"] = (q.get("view") or [""])[0]
    return out


def cell_to_text(v) -> str:
    """把一个单元格的值归一化成字符串（飞书字段类型很多，要逐个兜住）。"""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "是" if v else ""
    if isinstance(v, (int, float)):
        # 13 位毫秒时间戳按日期还原（飞书日期字段就是这个形态）
        if 1_000_000_000_000 <= v < 100_000_000_000_000:
            import datetime
            try:
                return datetime.datetime.fromtimestamp(v / 1000).strftime("%Y-%m-%d")
            except (OverflowError, OSError, ValueError):
                return str(int(v))
        return str(v)
    if isinstance(v, str):
        return "" if v.strip() in _EMPTY else v.strip()
    if isinstance(v, dict):
        # 超链接 {link, text} / 人员 {name} / 附件 {name, url} / 富文本 {text}
        for k in ("link", "url"):
            if v.get(k):
                return str(v[k]).strip()
        for k in ("text", "name", "en_name", "full_name"):
            if v.get(k):
                return str(v[k]).strip()
        return "" if not v else json.dumps(v, ensure_ascii=False)[:200]
    if isinstance(v, (list, tuple)):
        parts = [cell_to_text(x) for x in v]
        # 富文本字段常是 [{"text": ...}] 这种一段段拼起来
        return "".join(p for p in parts if p) if all(isinstance(x, dict) for x in v) \
            else " / ".join(p for p in parts if p)
    return str(v).strip()


def records_to_table(records) -> tuple:
    """记录列表 → (headers, rows)。

    兼容两种形态：
      - 连接器/官方 API：[{"record_id": "...", "fields": {...}}, ...]
      - 简化版：[{"岗位": "...", "公司": "..."}, ...]
    """
    headers, seen = [], set()
    for rec in records or []:
        fields = rec.get("fields") if isinstance(rec, dict) and "fields" in rec else rec
        if not isinstance(fields, dict):
            continue
        for k in fields:
            k = str(k)
            if k not in seen:
                seen.add(k)
                headers.append(k)
    rows = []
    for rec in records or []:
        fields = rec.get("fields") if isinstance(rec, dict) and "fields" in rec else rec
        if not isinstance(fields, dict):
            continue
        row = [cell_to_text(fields.get(h)) for h in headers]
        if any(row):
            rows.append(row)
    return headers, rows


def records_to_tsv(records) -> str:
    """转成 TSV 文本（交给 importer 的表头别名识别）。

    用制表符而不是逗号：岗位描述里逗号太多，TSV 更不容易串行。
    含制表符/换行的单元格包上双引号（importer 已支持带引号的多行单元格）。
    """
    headers, rows = records_to_table(records)
    if not headers:
        return ""
    def esc(s):
        s = str(s).replace("\t", " ")
        if "\n" in s or '"' in s:
            return '"' + s.replace('"', '""') + '"'
        return s
    lines = ["\t".join(esc(h) for h in headers)]
    for r in rows:
        lines.append("\t".join(esc(c) for c in r))
    return "\r\n".join(lines)


def import_records(records, source: str = "飞书多维表格") -> dict:
    """把飞书记录直接写进岗位库。返回 importer 的结果 dict。"""
    tsv = records_to_tsv(records)
    if not tsv:
        return {"rows": 0, "inserted": 0, "warnings": ["这份记录里没有任何字段，可能是连错表了"]}
    return importer.import_csv_text(tsv, source=source)


def load_json_file(path: str):
    """读连接器导出的 JSON（可能是 list，也可能包在 {"records": [...]} 里）。"""
    with io.open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        for k in ("records", "items", "data", "rows"):
            if isinstance(data.get(k), list):
                return data[k]
        return [data]
    return data


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="把飞书多维表格的连接器导出 JSON 导入岗位库")
    ap.add_argument("json_file", help="连接器导出的 JSON 文件")
    ap.add_argument("--source", default="飞书多维表格", help="来源标记（默认 飞书多维表格）")
    ap.add_argument("--url", default="", help="顺带解析表链接，确认 app_token / table_id")
    a = ap.parse_args(argv)

    if a.url:
        info = parse_base_url(a.url)
        print("表链接解析：")
        for k, v in info.items():
            print(f"  {k:10s} {v}")
        print()

    recs = load_json_file(a.json_file)
    print(f"读到 {len(recs)} 条记录")
    res = import_records(recs, source=a.source)
    print(f"导入：行 {res.get('rows')} / 新增 {res.get('inserted')}")
    if res.get("warnings"):
        for w in res["warnings"]:
            print("  ! " + str(w))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
