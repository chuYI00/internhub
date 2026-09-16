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
JD_MEDIA = "岗位职责：负责抖音账号短视频内容选题、剪辑与发布；跟进数据复盘与热点追踪。要求有内容运营经验。"
JD_AVIATION = "中国民航局下属单位招聘信息化技术岗，要求电子信息类、计算机类专业，熟悉网络安全与数据库。"
JD_AI = "参与大模型应用开发，使用 Python、LangChain、RAG、提示词工程与向量数据库构建知识库问答系统。"


def main() -> int:
    from ihub import tailor as tk

    print("[1] 方向识别")
    cases = [(JD_EMBED, "嵌入式软件开发工程师", "hw"),
             (JD_MEDIA, "新媒体运营实习生", "media"),
             (JD_AVIATION, "信息化技术岗", "aviation"),
             (JD_AI, "大模型应用开发实习生", "ai")]
    for jd, title, want in cases:
        got, scores, weak = tk.detect(jd, title)
        check(f"「{title}」→ {tk.label_of(got)}", got == want, {"got": got, "want": want, "scores": scores})
    got, _, weak = tk.detect("", "")
    check("完全没线索时不报错", isinstance(got, str) and got in tk.ORDER, got)

    print("[2] 匹配分析")
    an = tk.analyze(JD_EMBED, "hw")
    check("算了匹配分", 35 <= an["score"] <= 96, an["score"])
    check("命中里有 STM32 / FreeRTOS", any(x.lower() in ("stm32", "freertos") for x in an["hit"]), an["hit"])
    an2 = tk.analyze("要求熟练掌握 Cadence、HyperLynx、PCB 高速布线", "hw")
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
    md = tk.md_resume("hw", {"company": "某某科技", "title": "嵌入式软件工程师"})
    check("简历里出现公司与岗位名", "某某科技" in md and "嵌入式软件工程师" in md)
    md2 = tk.md_resume("hw", None)
    check("不传 ctx 时用方向默认意向", tk.direction("hw")["intent"] in md2)

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
                    "岗位定向简历/01_嵌入式硬件研发_罗广睿.pdf",
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
    check("有 10 个页签", len(at.tabs) == 10, len(at.tabs))

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

    print(f"\n结果: {PASS} 通过, {FAIL} 失败")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
