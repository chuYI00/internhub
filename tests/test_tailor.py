# -*- coding: utf-8 -*-
"""简历定制链路自测：方向识别 / 匹配分析 / 网申文案 / 单页排版 / 网页页签。

运行： venv\\Scripts\\python.exe tests\\test_tailor.py

设计意图：
- 定向简历最容易出的问题是"内容变多挤成两页"，这里用 pypdf 数页数守住"必须 1 页"。
- 「简历定制」页签是交互式生成的，这里用 AppTest 真的填一段 JD 跑一遍，确认页面不炸。
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


JD_EMBED = ("岗位职责：负责物联网终端设备嵌入式软件设计与开发；参与硬件方案评审，完成驱动调试与"
            "通信协议实现（UART/I2C/SPI/MQTT）。任职要求：本科及以上，电子信息、自动化、计算机相关专业；"
            "熟悉 C 语言与 STM32 开发，了解 FreeRTOS 者优先。")
JD_EE = ("岗位职责：负责原理图设计与 PCB Layout，完成样机焊接调试与电气性能测试；"
         "编写器件选型与 BOM，处理 EMC / 信号完整性问题。要求电子、电气类专业，会看 datasheet。")
JD_MFG = ("招聘岗位：自动化设备工程师。负责非标自动化产线 PLC 程序编写与调试、伺服参数设置、"
          "机器视觉工位部署，参与设备验收与节拍优化。")
JD_AVIATION = "中国民航局下属单位招聘信息化技术岗，要求电子信息类、计算机类专业，熟悉网络安全与数据库。"
JD_AI = "参与大模型应用开发，使用 Python、LangChain、RAG、提示词工程与向量数据库构建知识库问答系统。"
JD_SOE = ("云南省烟草公司下属单位招聘技术岗，要求本科及以上，电子信息 / 自动化 / 机电类专业，"
          "负责生产设备电气维护与信息化系统运维，需服从分配、能适应倒班。")


def main() -> int:
    from ihub import tailor as tk

    print("[1] 方向识别（8 个新方向）")
    cases = [(JD_EMBED, "嵌入式软件开发工程师", "iotembed"),
             (JD_EE, "硬件工程师", "ee"),
             (JD_MFG, "自动化设备工程师", "mfg"),
             (JD_AVIATION, "信息化技术岗", "soe"),
             (JD_AI, "大模型应用开发实习生", "aiapp"),
             (JD_SOE, "机电技术岗（烟草）", "soe")]
    for jd, title, want in cases:
        got, scores, weak = tk.detect(jd, title)
        check(f"「{title}」→ {tk.label_of(got)}", got == want, {"got": got, "want": want, "scores": scores})
    got, _, weak = tk.detect("", "")
    check("完全没线索时兜底到管培生", got == tk.FALLBACK_DIR, got)

    print("[2] 匹配分析")
    an = tk.analyze(JD_EMBED, "iotembed")
    check("算了匹配分", 35 <= an["score"] <= 96, an["score"])
    check("命中里有 STM32 / FreeRTOS", any(x.lower() in ("stm32", "freertos") for x in an["hit"]), an["hit"])
    an2 = tk.analyze("要求熟练掌握 Cadence、HyperLynx、PCB 高速布线", "ee")
    check("没做过的技术会进 miss 而不是硬编进去", "Cadence" in an2["miss"], an2["miss"])

    print("[3] 各方向内容齐备")
    for key in ["universal"] + list(tk.ORDER):
        pack = tk.fill_pack(key, {"company": "某公司", "title": "某岗位"})
        d = tk.direction(key)
        ok = (len(pack) >= 20 and len(d["selfeval"]) > 80
              and len(d["highlights"]) >= 4 and len(d["skill_order"]) >= 4 and len(d["projects"]) >= 3)
        check(f"{tk.label_of(key)} 文案完整（{len(pack)} 项）", ok)

    print("[4] 单页排版（docx + pdf）")
    tmp = tempfile.mkdtemp(prefix="ihub_cv_")
    try:
        from pypdf import PdfReader
        has_pypdf = True
    except Exception as e:                       # noqa: BLE001
        has_pypdf = False
        print("  (未安装 pypdf，跳过页数校验：pip install pypdf)")
        _ = e
    for key in ["universal"] + list(tk.ORDER):
        dx = os.path.join(tmp, f"{key}.docx")
        tk.resume_docx(key, dx, {"company": "某公司", "title": "某岗位"})
        check(f"{tk.label_of(key)} docx 生成", os.path.getsize(dx) > 20000, os.path.getsize(dx))
        if has_pypdf:
            try:
                pdf = os.path.join(tmp, f"{key}.pdf")
                tk.build_pdf(key, pdf, {"company": "某公司", "title": "某岗位"})
                n = len(PdfReader(pdf).pages)
                check(f"{tk.label_of(key)} pdf 正好 1 页", n == 1, n)
            except Exception as e:               # noqa: BLE001
                check(f"{tk.label_of(key)} pdf 生成", False, str(e))

    print("[5] 求职意向带上目标公司/岗位")
    md = tk.md_resume("iotembed", {"company": "某某科技", "title": "嵌入式软件工程师"})
    check("简历里出现公司与岗位名", "某某科技" in md and "嵌入式软件工程师" in md)
    md2 = tk.md_resume("iotembed", None)
    check("不传 ctx 时用方向默认意向", tk.direction("iotembed")["intent"] in md2)

    print("[6] 速填卡 / 脚本资料包")
    qc = tk.quickcard()
    check("速填卡含学院", "电子信息与自动化学院" in qc)
    check("速填卡含 8 个方向", sum(1 for k in tk.ORDER if tk.label_of(k) in qc) == len(tk.ORDER))
    packs = tk.packs()
    check("脚本资料包 9 套", len(packs) == 9, list(packs))
    check("每套都有 label/self_eval/skills",
          all(p.get("label") and p.get("self_eval") and p.get("skills") for p in packs.values()))
    bf = tk.base_fields()
    check("基础资料含学院与 GPA", "电子信息与自动化" in bf["college"] and bf["gpa"].count("/") == 1, bf["college"])

    print("[7] 材料文件是否生成（跑过 gen_resume_kit.py 才有）")
    kit_dir = ROOT / "简历材料"
    if kit_dir.exists():
        for rel in ["02_万能通用版_罗广睿_中国民航大学.docx",
                    "岗位定向简历/01_物联网嵌入式开发_罗广睿.pdf",
                    "05_投递工作台.html", "04_网申速填卡.txt", "08_资料库.json"]:
            check(f"存在 {rel}", (kit_dir / rel).exists())
        html = (kit_dir / "05_投递工作台.html").read_text(encoding="utf-8")
        check("工作台已注入资料（含学院）", "电子信息与自动化学院" in html)
        check("工作台注入的是 9 套方向", html.count('"selfeval"') >= 9, html.count('"selfeval"'))
    else:
        print("  (还没跑 gen_resume_kit.py，跳过)")

    print("[8] 网页「简历定制」页签真跑一遍")
    tmpdir = tempfile.mkdtemp(prefix="ihub_tk_")
    from ihub import config
    if Path(config.DB_PATH).exists():
        shutil.copy2(config.DB_PATH, os.path.join(tmpdir, "jobs.db"))
    config.DB_PATH = os.path.join(tmpdir, "jobs.db")
    from ihub import db as db_mod
    db_mod.init_db()

    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
    at.run()
    check("app 无异常", not at.exception, [e.value for e in at.exception])
    check("有 4 个页签", len(at.tabs) == 4, len(at.tabs))

    at.text_area(key="tk_jd").set_value(JD_EMBED)
    at.text_input(key="tk_jt").set_value("嵌入式软件开发工程师")
    at.run()
    check("填 JD 后无异常", not at.exception, [e.value for e in at.exception])
    metrics = [m.value for m in at.metric]
    check("出现了「匹配度」指标", any("分" in str(v) for v in metrics), metrics)
    radios = [r for r in at.radio if r.key == "tk_dir"]
    check("方向选择器存在且默认识别为嵌入式",
          bool(radios) and any("嵌入式" in o for o in radios[0].options), 
          radios[0].options if radios else None)
    codes = [c.value for c in at.code]
    check("网申文案块已渲染（含学院）", any("电子信息与自动化学院" in c for c in codes), len(codes))
    check("文案块数量够（≥15）", len(codes) >= 15, len(codes))

    print("[9] 云南秋招情报库")
    from ihub import yunnan as yn
    units = yn.all_units()
    check("单位数量合理（≥20）", len(units) >= 20, len(units))
    check("分 8 个类别", len(yn.cats_in_order()) == 8, len(yn.cats_in_order()))
    check("烟草排在第一类", "烟草" in yn.cats_in_order()[0][0], yn.cats_in_order()[0][0])
    names = " ".join(u["name"] for u in units)
    for kw in ("烟草专卖局", "云南中烟", "南方电网", "云南航空产业投资"):
        check(f"含关键单位「{kw}」", kw in names)
    check("每条都有 对口岗位/节奏/提醒",
          all(u.get("fit") and u.get("rhythm") and u.get("tips") for u in units))
    check("每条都至少有一个可用入口（官方直达或搜索兜底）",
          all(u.get("portal") or u.get("apply") or u.get("search") for u in units))
    # 第 2 步重构：portal/apply 只允许企业自己的域名，搜索引擎链接一律清出去
    from ihub import linkcheck as _lc
    check("官方投递字段里没有伪直达（第 2 步硬标准）",
          not any(_lc.is_any_search(u.get(k) or "")
                  for u in units for k in ("portal", "apply")),
          [(u["name"], u.get(k)) for u in units for k in ("portal", "apply")
           if _lc.is_any_search(u.get(k) or "")])
    check("拿不到官方直达的会明说（不拿假直达冒充）",
          all(yn.has_official(u) or "搜索兜底" in u["apply_note"] for u in units))
    check("高契合单位 ≥10 家", len(yn.for_me()) >= 10, len(yn.for_me()))
    txt = yn.as_text()
    check("导出文本含烟草官网", "tobacco.gov.cn" in txt)
    check("导出文本含每周动作", "每周固定动作" in txt)
    check("烟草那条写明了「重复投递取消资格」",
          any("取消资格" in u["tips"] for u in units if "烟草" in u["name"]))
    check("链接都是 http(s)", all(
        (u.get("portal","").startswith("http") or not u.get("portal")) and
        (u.get("apply","").startswith("http") or not u.get("apply")) and
        u["search"].startswith("http") for u in units))

    print("[10] 全网平台矩阵")
    from ihub import platforms as PL
    plats = PL.all_platforms()
    check("平台数 ≥20", len(plats) >= 20, len(plats))
    check("分 4 大类", len(PL.cats_in_order()) == 4, len(PL.cats_in_order()))
    check("第一类是国家级官方", "国家级官方" in PL.cats_in_order()[0][0])
    names = " ".join(x["name"] for x in plats)
    for kw in ("国聘网", "24365", "BOSS直聘", "智联", "牛客", "应届生求职网",
               "云南人才网", "中国民航大学", "大理"):
        check(f"含平台「{kw}」", kw in names)
    check("每个平台都有 官网/适配/怎么筛", all(
        x["url"].startswith("http") and x["fit"] and x["how"] for x in plats))
    check("每条都标注了 是否需登录 + 能否自动抓", all(
        isinstance(x["login"], bool) and x["crawl"] for x in plats))
    check("有可自动抓的平台", len(PL.auto_crawlable()) >= 6, len(PL.auto_crawlable()))
    # 第 2 步重构：伪直达（百度 site: 站内搜）全部移除，改为「官方入口 + 该敲的词」
    from ihub import linkcheck as _lc2
    check("平台矩阵里再也没有百度/搜狗伪直达",
          not any(_lc2.is_fake_direct(x["url"]) for x in plats),
          [x["url"] for x in plats if _lc2.is_fake_direct(x["url"])])
    check("entry_links 全部是官方入口（不是搜索引擎页）",
          all(not _lc2.is_fake_direct(u) for _, u, _ in PL.entry_links()),
          [u for _, u, _ in PL.entry_links() if _lc2.is_fake_direct(u)])
    check("entry_links ≥20 条且都是 http(s)",
          len(PL.entry_links()) >= 20 and all(u.startswith("http") for _, u, _ in PL.entry_links()),
          len(PL.entry_links()))
    check("只有真支持站内搜索的平台才给搜索链接（24365）",
          sum(1 for x in plats if PL.in_site_search(x)) == 1,
          [x["name"] for x in plats if PL.in_site_search(x)])
    check("没有站内搜索的平台给了「该敲什么词」的说明",
          all(("关键词" in d or "站内搜索框" in d) for _, u, d in PL.entry_links()
              if "keyword=" not in u))
    check("今天该干什么 6 步", len(PL.today_plan()) == 6, len(PL.today_plan()))
    txt = PL.as_text()
    check("导出文本含 BOSS 与 应届生", "BOSS" in txt and "应届生" in txt)
    check("导出文本说明了「前端渲染抓不到」", "前端渲染" in txt)
    check("links_text 可直接复制（含 20 条链接）",
          PL.links_text().count("http") >= 20, PL.links_text().count("http"))

    print(f"\n结果: {PASS} 通过, {FAIL} 失败")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
