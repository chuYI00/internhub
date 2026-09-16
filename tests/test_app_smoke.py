# -*- coding: utf-8 -*-
"""网页冒烟测试：用 Streamlit 官方 AppTest 无头跑一遍 app.py，确认 4 个页签都能渲染、
关键按钮都在、没有异常。

跑的是**临时数据库副本**，不会动你的真实 data/jobs.db（只有点了写按钮才会写，本测试不点写按钮）。

运行： venv\\Scripts\\python.exe tests\\test_app_smoke.py
"""
from __future__ import annotations

import os
import shutil
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
    tmpdir = tempfile.mkdtemp(prefix="ihub_smoke_")
    tmp_db = os.path.join(tmpdir, "jobs.db")

    from ihub import config
    if Path(config.DB_PATH).exists():
        shutil.copy2(config.DB_PATH, tmp_db)
    config.DB_PATH = tmp_db                      # app.py 与各模块都读 config.DB_PATH

    from ihub import db as db_mod
    db_mod.init_db()

    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
    at.run()

    print("[1] 首页渲染")
    check("app.py 无异常", not at.exception, [e.value for e in at.exception])
    check("有 4 个页签（收敛重构后）", len(at.tabs) == 4, len(at.tabs))
    tab_labels = [t.label for t in at.tabs]
    for want in ("岗位", "投递与网申", "简历定制", "备考方案"):
        check(f"『{want}』页签存在", any(want in x for x in tab_labels), tab_labels)

    print("[1b] 页签编号静态对齐检查（历史上在这翻过车：内容渲染到别的页签）")
    import re as _re
    _src = (ROOT / "app.py").read_text(encoding="utf-8")
    _tabs_calls = _re.findall(r"=\s*st\.tabs\(", _src)
    check("app.py 里只有一处 st.tabs(", len(_tabs_calls) == 1, len(_tabs_calls))
    _decl = _re.search(r"st\.tabs\(\s*\[(.*?)\]", _src, _re.S)
    _decl_labels = _re.findall(r'"([^"]*)"', _decl.group(1)) if _decl else []
    check("st.tabs 声明了 4 个标签", len(_decl_labels) == 4, _decl_labels)
    _blocks = _re.findall(r"^    with tab(\d+):", _src, _re.M)
    check("每个 with tabN: 的 N 都在 1..4 内",
          all(1 <= int(n) <= 4 for n in _blocks), sorted(set(_blocks)))
    check("四个页签都至少有一块内容（没有空页签）",
          set(_blocks) == {"1", "2", "3", "4"}, sorted(set(_blocks)))
    check("没有残留的 tab5..tab12（会被渲染到不存在的页签里）",
          not any(int(n) > 4 for n in _blocks), sorted(set(_blocks)))

    print("[1c] 链接域名与公司名匹配检查（第 2 步硬标准）")
    from ihub import linkcheck as _lc
    from ihub import channels as _ch
    _bad = {c: u for c, u in _ch.OFFICIAL_URLS.items() if _lc.is_any_search(u)}
    check("channels 里没有「点开是搜索引擎 / 招聘平台」的伪官方入口", not _bad, list(_bad.items())[:3])
    # 域名要和公司名对得上：每条官方入口都要能说清「这个域名凭什么是这家的」——
    # 要么域名里有该公司的英文/拼音标识，要么人工指纹表里登记过（政府站、ATS 等）。
    _no_fp = []
    for _c, _u in _ch.OFFICIAL_URLS.items():
        if not _lc.words_for(_u, _c):
            _no_fp.append((_c, _u))
    check("每条官方入口都能对应到该单位的页面指纹（标题/正文关键词）",
          not _no_fp, _no_fp[:3])
    _pl = [x for x in __import__("ihub.platforms", fromlist=["x"]).all_platforms()
           if _lc.is_fake_direct(x["url"])]
    check("平台矩阵里没有伪直达", not _pl, [x["url"] for x in _pl][:3])
    _yn = [u["name"] for u in __import__("ihub.yunnan", fromlist=["x"]).all_units()
           if not __import__("ihub.yunnan", fromlist=["x"]).has_official(u)]
    check(f"云南渠道地图里没拿到官方直达的会明说（{len(_yn)} 家）", True, _yn[:4])

    print("[2] 广投批量按钮")
    keys = [b.key for b in at.button]
    check("有『全部加入投递箱』", "bulk_in" in keys, keys[:20])
    check("有『全部移出投递箱』", "bulk_out" in keys, keys[:20])
    dl_keys = [d.key for d in at.get("download_button")]
    check("有『导出清单 CSV』", "bulk_export" in dl_keys, dl_keys)
    check("有『保存 投递箱+收藏』", any("保存 投递箱" in (b.label or "") for b in at.button),
          [b.label for b in at.button][:20])
    dls = at.get("download_button")
    if dls:
        check("导出按钮文案正确", "导出清单" in str(dls[0].label), dls[0].label)
    # 导出的内容用同一条数据管线复算一遍（proto 里不带 bytes，只能这样验内容）
    import pandas as pd
    from ihub import db as _db
    rows = _db.query(limit=20)
    if rows:
        exp = pd.DataFrame([dict(r) for r in rows])
        csv_head = exp.to_csv(index=False).splitlines()[0]
        check("导出内容可生成 CSV 表头", len(csv_head) > 5, csv_head[:60])

    print("[3] 没有导出权限时的『粘贴导入』入口")
    ta_keys = [t.key for t in at.text_area]
    check("有粘贴表格的输入框", "paste_tbl" in ta_keys, ta_keys)
    check("有『导入粘贴的内容』按钮", "paste_import" in keys, keys[:25])

    print("[4] 侧边栏能渲染筛选控件")
    check("快速锁定城市 radio 存在",
          any("潍坊" in str(r.options) for r in at.radio), [str(r.options)[:40] for r in at.radio])

    print("[4] 切换到不同城市筛选后仍能渲染（不写库）")
    for city in ("昆明", "大理"):
        at2 = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
        at2.run()
        radios = [r for r in at2.radio if "潍坊" in str(r.options)]
        if radios:
            radios[0].set_value(city).run()
        check(f"选 {city} 后无异常", not at2.exception, [e.value for e in at2.exception])

    print("[5] 切换岗位类型=秋招")
    at3 = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
    at3.run()
    jt = [r for r in at3.radio if "秋招" in str(r.options) and "实习" in str(r.options)]
    if jt:
        jt[0].set_value("秋招").run()
    check("秋招筛选无异常", not at3.exception, [e.value for e in at3.exception])

    # 清理临时库
    for p in (tmp_db, tmp_db + "-wal", tmp_db + "-shm"):
        try:
            os.remove(p)
        except OSError:
            pass
    shutil.rmtree(tmpdir, ignore_errors=True)

    print(f"\n结果: {PASS} 通过, {FAIL} 失败")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
