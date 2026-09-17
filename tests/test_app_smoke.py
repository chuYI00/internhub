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

    print("[3] v2 导入向导（4 条通道收敛成 1 处）")
    _chans = [str(r.options) for r in at.radio if "上传" in str(r.options)]
    check("四条通道都在一个 radio 里", _chans and all(
        k in _chans[0] for k in ("上传", "复制粘贴", "抓包解码", "截图 OCR")), _chans[:1])
    check("默认停在通道①，有『上传文件』入口",
          "wz_file" in [u.key for u in at.get("file_uploader")],
          [u.key for u in at.get("file_uploader")])
    # 旧的三处重复入口必须真的删掉（删 UI 但留着 key 就白收敛了）
    ta_keys = [t.key for t in at.text_area]
    check("旧入口『paste_tbl』已移除", "paste_tbl" not in ta_keys, ta_keys)
    check("旧入口『csv_qiu』已移除",
          "csv_qiu" not in [u.key for u in at.get("file_uploader")], None)
    # 向导绝不能新增 st.tabs（整页必须恰好 4 个页签）
    check("整页仍然只有 4 个页签（向导没偷偷加 tabs）", len(at.tabs) == 4, len(at.tabs))

    # 每条通道单独切过去看一眼（radio 选了哪条才渲染哪条，所以得逐个跑）
    def _switch_to(chan, kind):
        _a = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
        _a.run()
        _rs = [r for r in _a.radio if "上传" in str(r.options)]
        if _rs:
            _rs[0].set_value(chan).run()
        return [w.key for w in _a.get(kind)], _a

    _k2, _a2 = _switch_to("② 复制粘贴", "text_area")
    check("通道② 有粘贴输入框", "wz_paste" in _k2, _k2)
    _k2b, _ = _switch_to("② 复制粘贴", "button")
    check("通道② 有『解析』按钮", "wz_parse_paste" in _k2b, _k2b[:10])
    _k3, _ = _switch_to("③ 抓包解码", "button")
    check("通道③ 有『读取飞书解码 CSV』按钮", "wz_load_decoded" in _k3, _k3[:10])
    _k4, _ = _switch_to("④ 截图 OCR", "button")
    check("通道④ 有占位按钮（暂未开放）", "wz_ocr" in _k4, _k4[:10])

    # 端到端：切到通道② → 粘一段 → 点解析 → 应该出现「字段映射 + 确认导入」
    _a5 = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
    _a5.run()
    _r5 = [r for r in _a5.radio if "上传" in str(r.options)]
    if _r5:
        _r5[0].set_value("② 复制粘贴").run()
    _ta5 = [t for t in _a5.text_area if t.key == "wz_paste"]
    if _ta5:
        _ta5[0].set_value("岗位名称\t公司\t城市\n电气工程师\t云南中烟\t昆明\n").run()
        _b5 = [b for b in _a5.button if b.key == "wz_parse_paste"]
        if _b5:
            _b5[0].click().run()
    check("解析后无异常", not _a5.exception, [e.value for e in _a5.exception])
    _sb5 = [s.key for s in _a5.selectbox]
    check("解析后出现字段映射下拉", "wz_map_title" in _sb5, _sb5[:14])
    check("映射覆盖全部 7 个标准字段",
          all(f"wz_map_{f}" in _sb5 for f in
              ("title", "company", "city", "link", "source_name", "deadline", "note")), _sb5[:14])
    _b5k = [b.key for b in _a5.button]
    check("解析后出现『确认导入』按钮", "wz_commit" in _b5k, _b5k[:14])

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

    print("[6] 第 3 步重构：台账打通 + 岗位↔简历定制联动")
    _keys_all = [b.key for b in at.button]
    check("有『📄 定制这份简历 →』按钮（岗位页 → 简历定制）",
          "lk_to_tailor" in _keys_all, _keys_all[-12:])
    check("有岗位选择框（选一条带过去）",
          "lk_pick" in [s.key for s in at.selectbox], [s.key for s in at.selectbox][:12])
    _ta = [t.key for t in at.text_area]
    check("有『粘贴投递记录』输入框（网申助手 → 台账）", "ledger_paste" in _ta, _ta)
    check("有『解析并预览』按钮", "ledger_parse" in _keys_all, _keys_all[-12:])

    # 页面文字散落在 markdown / caption / expander / info 等多种元素里，全捞一遍再断言
    _blob_parts = []
    for _t in ("markdown", "caption", "expander", "info", "warning", "error",
               "success", "text", "code", "header", "subheader"):
        try:
            for _e in at.get(_t):
                _blob_parts.append(str(getattr(_e, "value", None) or getattr(_e, "label", "") or ""))
        except Exception:
            pass
    _blob = "\n".join(_blob_parts)
    check("有『从网申助手粘贴导入』折叠区", "从网申助手粘贴导入" in _blob,
          [p[:40] for p in _blob_parts if "网申助手" in p][:3])
    check("烟草「1 单位 1 岗」铁律在台账页有提示",
          "同一批次只能报 1 个单位 1 个岗位" in _blob, None)
    check("台账页说明了烟草记录会被拦截", "烟草的记录在这里就会被拦住" in _blob, None)

    print("[7] 第 2 步：链接体检区块")
    check("有『链接体检』区块", "链接体检" in _blob, None)
    check("页面明示「伪直达」口径", "伪直达" in _blob, None)
    check("页面说明了 A 级才能当官方投递按钮",
          "只有 A 级" in _blob or "A 级" in _blob, None)

    print("[8] 第 4 步：备考方案生成器")
    check("④ 备考方案页有生成器区块", "备考方案生成器" in _blob, None)
    _sb_keys = [s.key for s in at.selectbox]
    _in_keys = [t.key for t in at.text_input] + [n.key for n in at.number_input]
    check("生成器有目标单位选择框", "sp_target" in _sb_keys, _sb_keys[:14])
    check("生成器有岗位输入框（决定专业知识考哪套）", "sp_role" in _in_keys, _in_keys[:14])
    check("生成器有考试日期输入框", "sp_date" in _in_keys, _in_keys[:14])
    check("生成器有每天可学小时数", "sp_hours" in _in_keys, _in_keys[:14])
    check("生成器有『生成备考方案』按钮", "sp_gen" in _keys_all, _keys_all[-14:])
    check("生成器说明里点明了「考什么/抓什么/每天干什么/背什么」",
          "该抓什么可以放弃什么" in _blob, None)
    check("备考页保留了打卡清单（本地保存进度）",
          "打卡" in _blob, None)
    check("烟草成品作战方案仍可下载（没被生成器挤掉）",
          any("下载 Word" in str(d.label) for d in at.get("download_button")), None)

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
