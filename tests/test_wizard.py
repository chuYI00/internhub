# -*- coding: utf-8 -*-
"""导入向导（v2 重构任务一）自测。

覆盖四条通道的**解析层**（纯逻辑，不跑 Streamlit）：
  · 复制粘贴：制表符 / 逗号 / 无表头（按内容猜列，第一行不能丢）
  · 上传文件：CSV（含 BOM、gbk）、xlsx（不装 openpyxl 也要能读）
  · 抓包解码：模拟一份 `H4sI` 开头的 gzip+base64，走完 解码 → CSV → 向导解析
  · 映射：乱列名（"公司名称/单位/雇主"）→ 标准字段；未映射列并进备注不丢
  · 入库去重：同样一条导两次，第二次只更新不新增

运行： venv\\Scripts\\python.exe tests\\test_wizard.py
"""
from __future__ import annotations

import base64
import gzip
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PASS = 0
FAIL = 0


def check(name: str, cond: bool, extra=None) -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK] {name}")
    else:
        FAIL += 1
        print(f"  [XX] {name}" + (f"  -> {extra}" if extra is not None else ""))


def main() -> int:
    from ihub import config, db

    # 用临时库，别动真实数据
    tmpdir = tempfile.mkdtemp(prefix="ihub_wizard_")
    tmp_db = os.path.join(tmpdir, "jobs.db")
    config.DB_PATH = tmp_db
    from ihub import db as db2
    db2.DB_PATH = tmp_db
    db2.init_db()

    from ihub import wizard as wz

    print("[1] 通道② 复制粘贴：制表符（飞书/Excel 复制出来的就是 TSV）")
    tsv = ("岗位名称\t公司名称\t工作城市\t投递链接\t报名截止\n"
           "电气工程师\t云南中烟工业\t昆明\thttps://www.ynzy-tobacco.com/\t2026-12-06\n"
           "信息化岗\t云南省烟草专卖局\t大理\thttps://yn.tobacco.gov.cn/\t2026-12-06\n")
    r = wz.parse_text(tsv, source="粘贴")
    check("解析出表头 5 列", len(r["headers"]) == 5, r["headers"])
    check("解析出 2 行数据（表头不被当数据）", len(r["rows"]) == 2, len(r["rows"]))
    check("认出表头", r["has_header"], None)
    mp = wz.guess_mapping(r["headers"], r["rows"])
    check("岗位名称→0", mp.get("title") == 0, mp)
    check("公司名称→1（乱列名也能映射）", mp.get("company") == 1, mp)
    check("工作城市→2", mp.get("city") == 2, mp)
    check("投递链接→3", mp.get("link") == 3, mp)
    check("报名截止→4", mp.get("deadline") == 4, mp)
    jobs, skipped = wz.build_jobs(r["headers"], r["rows"], mp, source="粘贴")
    check("转出 2 条待入库", len(jobs) == 2, len(jobs))
    check("公司字段取对", jobs[0]["company"] == "云南中烟工业", jobs[0]["company"])
    check("链接字段取对", jobs[0]["link"].startswith("https://"), jobs[0]["link"])

    print("[2] 通道② 无表头（飞书里只框选了数据行）")
    nohead = ("电气工程师\t云南中烟工业\t昆明\thttps://www.ynzy-tobacco.com/\t2026-12-06\n"
              "信息化岗\t云南省烟草专卖局\t大理\thttps://yn.tobacco.gov.cn/\t2026-12-06\n")
    r2 = wz.parse_text(nohead, source="粘贴")
    check("提示了没表头", any("没识别到表头" in w for w in r2["warnings"]), r2["warnings"])
    check("第一行没被吃掉（2 行都在）", len(r2["rows"]) == 2, len(r2["rows"]))
    mp2 = wz.guess_mapping(r2["headers"], r2["rows"])
    check("按内容猜出了链接列", mp2.get("link") == 3, mp2)
    check("按内容猜出了公司列", mp2.get("company") == 1, mp2)
    check("按内容猜出了截止列", mp2.get("deadline") == 4, mp2)

    print("[3] 通道② 逗号 CSV + BOM + 岗位名里带逗号")
    csv_text = ("\ufeff岗位,公司,城市\n"
                '"设备运维,设备管理",云南中烟,昆明\n'
                "信息化岗,云南机场集团,大理\n")
    r3 = wz.parse_text(csv_text, source="CSV")
    check("BOM 不影响首列名", r3["headers"][0] == "岗位", r3["headers"])
    check("带逗号的岗位名没被切坏", r3["rows"][0][0] == "设备运维,设备管理", r3["rows"][0])
    check("2 行数据", len(r3["rows"]) == 2, len(r3["rows"]))

    print("[4] 通道① 上传文件：CSV（gbk 也能读）+ xlsx（不装 openpyxl 也要能读）")
    r4 = wz.parse_bytes("jobs.csv", csv_text.encode("utf-8-sig"), source="文件")
    check("CSV 文件解析出 2 行", len(r4["rows"]) == 2, len(r4["rows"]))
    gbk = "岗位,公司,城市\n电气工程师,云南电网,昆明\n".encode("gbk")
    r4b = wz.parse_bytes("jobs_gbk.csv", gbk)
    check("gbk 编码不乱码", r4b["rows"] and r4b["rows"][0][0] == "电气工程师",
          r4b["rows"][:1])
    # 造一个最小 xlsx（zip + xml），验证内置 reader
    xlsx = _make_xlsx([["岗位名称", "公司名称", "城市"],
                       ["弱电工程师", "云南航产投", "昆明"],
                       ["运维岗", "大理机场", "大理"]])
    r5 = wz.parse_bytes("jobs.xlsx", xlsx)
    check("xlsx 解析出表头 3 列", len(r5["headers"]) == 3, r5["headers"])
    check("xlsx 解析出 2 行", len(r5["rows"]) == 2, len(r5["rows"]))
    check("xlsx 内容正确", r5["rows"][0][0] == "弱电工程师" and r5["rows"][1][1] == "大理机场",
          r5["rows"])
    mp5 = wz.guess_mapping(r5["headers"], r5["rows"])
    jobs5, _ = wz.build_jobs(r5["headers"], r5["rows"], mp5, source="xlsx")
    check("xlsx 也能转出岗位", len(jobs5) == 2 and jobs5[0]["company"] == "云南航产投", jobs5[:1])

    print("[5] 通道③ 抓包解码：模拟 H4sI 开头的 gzip+base64")
    payload = {"data": {"records": [
        {"fields": {"岗位名称": "电气工程师", "公司名称": "云南中烟工业",
                    "工作城市": "昆明", "投递链接": "https://www.ynzy-tobacco.com/"}},
        {"fields": {"岗位名称": "信息化岗", "公司名称": "云南省烟草专卖局",
                    "工作城市": "大理", "投递链接": "https://yn.tobacco.gov.cn/"}},
    ]}}
    blob = base64.b64encode(gzip.compress(json.dumps(payload, ensure_ascii=False).encode("utf-8"))).decode()
    check("模拟数据确实是 H4sI 开头", blob.startswith("H4sI"), blob[:8])
    # 走一遍真实解码器（项目根的 解码飞书表格.py），验证通道③ 端到端可跑
    decoded_csv = _run_decoder(blob, tmpdir)
    check("解码器产出了 CSV", bool(decoded_csv) and os.path.exists(decoded_csv or ""), decoded_csv)
    if decoded_csv:
        txt = getattr(_run_decoder, "last_text", "") or ""
        r6 = wz.parse_text(txt, source="飞书抓包解码")
        check("解码后的 CSV 能被向导解析", len(r6["rows"]) >= 2, len(r6["rows"]))
        mp6 = wz.guess_mapping(r6["headers"], r6["rows"])
        check("解码后仍能映射出岗位列", mp6.get("title") is not None, mp6)
    # 直接读 data/飞书岗位导出.csv 的接口也不能崩
    st = wz.load_decoded_csv(os.path.join(tmpdir, "不存在的.csv"))
    check("CSV 不存在时给出明确提示（不抛异常）", st.get("ok") is False and "还没生成" in st.get("msg", ""), st)

    print("[6] 映射不到的列并进备注，不丢信息")
    messy = ("岗位\t单位\t地点\t网址\t备注\t其他说明\n"
             "嵌入式工程师\t昆明船舶设备集团\t昆明\thttps://example.com/job\t国企正式编\t需要倒班\n")
    rm = wz.parse_text(messy, source="乱列名")
    mpm = wz.guess_mapping(rm["headers"], rm["rows"])
    used = set(mpm.values())
    check("乱列名「单位」映射到公司", mpm.get("company") == 1, mpm)
    check("乱列名「网址」映射到链接", mpm.get("link") == 3, mpm)
    jobs_m, _ = wz.build_jobs(rm["headers"], rm["rows"], mpm, source="乱列名")
    note = jobs_m[0]["description"] if jobs_m else ""
    check("未映射列（其他说明）并进备注", "其他说明：需要倒班" in note, note)
    check("备注列本身也保留", "国企正式编" in note, note)

    print("[7] 入库 + 去重（同一条导两次只能有一条）")
    res1 = wz.commit(jobs)
    res2 = wz.commit(jobs)
    check("第一次新增 2 条", res1.get("inserted") == 2, res1)
    check("第二次不再新增", res2.get("inserted") == 0, res2)
    rows = db2.query(limit=100)
    check("库里确实只有 2 条", len(rows) == 2, len(rows))
    check("岗位类型默认秋招", all(r["job_type"] == "秋招" for r in rows),
          [r["job_type"] for r in rows])

    print("[8] 边界：空输入 / 全是空行 / 只有表头")
    for name, txt in (("空字符串", ""), ("只有空行", "\n\n\n"), ("只有表头", "岗位,公司\n")):
        rr = wz.parse_text(txt)
        check(f"{name}：不崩且 0 行", rr["rows"] == [] or len(rr["rows"]) == 0, rr["rows"])
    rb = wz.parse_bytes("坏.xlsx", b"not a zip at all")
    check("坏 xlsx 给出可读报错而不是崩溃",
          any("另存为 CSV" in w for w in rb.get("warnings") or []), rb.get("warnings"))

    for p in (tmp_db, tmp_db + "-wal", tmp_db + "-shm"):
        try:
            os.remove(p)
        except OSError:
            pass
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)

    print(f"\n结果: {PASS} 通过, {FAIL} 失败")
    return 1 if FAIL else 0


def _make_xlsx(rows) -> bytes:
    """手搓一个最小 xlsx（zip + sheet1.xml + sharedStrings.xml），用来测内置 reader。"""
    import zipfile, io
    NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    strings, sheet_rows = [], []
    for ri, row in enumerate(rows, 1):
        cells = []
        for ci, val in enumerate(row):
            ref = chr(ord("A") + ci) + str(ri)
            try:
                si = strings.index(val)
            except ValueError:
                strings.append(val)
                si = len(strings) - 1
            cells.append(f'<c r="{ref}" t="s"><v>{si}</v></c>')
        sheet_rows.append(f'<row r="{ri}">{"".join(cells)}</row>')
    sheet = ('<?xml version="1.0" encoding="UTF-8"?>'
             f'<worksheet xmlns="{NS}"><sheetData>{"".join(sheet_rows)}</sheetData></worksheet>')
    shared = ('<?xml version="1.0" encoding="UTF-8"?>'
              f'<sst xmlns="{NS}" count="{len(strings)}">'
              + "".join(f"<si><t>{s}</t></si>" for s in strings) + "</sst>")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/worksheets/sheet1.xml", sheet)
        z.writestr("xl/sharedStrings.xml", shared)
    return buf.getvalue()


def _run_decoder(blob: str, tmpdir: str):
    """调用项目根的 解码飞书表格.py，返回它产出的 CSV 路径（失败返回 None）。

    解码器固定往 `data/飞书岗位导出.csv` 写，测试会**先备份再还原**，
    不会把用户真实的解码结果冲掉（这份文件是用户的，不是测试资产）。
    """
    import shutil
    import subprocess
    script = ROOT / "解码飞书表格.py"
    out_csv = ROOT / "data" / "飞书岗位导出.csv"
    if not script.exists():
        return None
    backup = None
    if out_csv.exists():
        backup = os.path.join(tmpdir, "orig.csv")
        shutil.copy2(out_csv, backup)
    src = os.path.join(tmpdir, "抓包.txt")
    with open(src, "w", encoding="utf-8") as f:
        f.write(blob)
    r = subprocess.run([sys.executable, str(script), src],
                       cwd=str(ROOT), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    ok = (r.returncode == 0 and out_csv.exists())
    path = str(out_csv) if ok else None
    # 读完内容后再还原 —— 返回值只给路径，调用方会立刻读一遍
    if path:
        with open(path, encoding="utf-8-sig") as f:
            _run_decoder.last_text = f.read()
    if backup:
        shutil.copy2(backup, out_csv)
    return path


if __name__ == "__main__":
    raise SystemExit(main())
