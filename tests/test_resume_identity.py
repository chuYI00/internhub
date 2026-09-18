# -*- coding: utf-8 -*-
"""简历「个人信息真值」防线。

背景：曾发生过 `ihub/profile.py` 里躺着一个占位手机号 13800000000，最后被真的填进了
网申表单——投递出去的东西，联系方式是错的。这个测试就是那次事故的长期防线。

它做的事：
1. 以 data/resume_kit.json 的 profile 为唯一真值源；
2. 逐份读 通用版 + 8 份定向版 的 docx / pdf / txt，断言姓名、手机、邮箱、
   学校学院专业、GPA、四六级全部与真值一致；
3. 断言没有出现任何「假号码 / 示例邮箱 / 潍坊残留」；
4. 断言 pdf 只有 1 页（超页的简历 HR 不看第二页）；
5. 顺带查网申速填卡、投递工作台、资料库 JSON 里的联系方式；
6. 断言代码库里再也不会出现占位手机号（DEFAULT 必须留空）。

运行： venv\\Scripts\\python.exe tests\\test_resume_identity.py
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 历史上真实出现过的错值 —— 这些字符串只要在任何成品里再次出现，就直接判失败
BANNED = [
    "13800000000",          # 曾经的占位手机号
    "example@example.com",    # 曾经的示例邮箱
    "示例同学",
    "潍坊",                  # 歌尔投递的历史残留，绝不能出现在通用材料里
    "13500135000",          # 曾经的错号：简历写它、网申助手填 13349396104，两套号码并存过
]

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


def docx_text(path: Path) -> str:
    from docx import Document
    d = Document(str(path))
    out = [p.text for p in d.paragraphs]
    for t in d.tables:
        for row in t.rows:
            for cell in row.cells:
                out.append(cell.text)
    return "\n".join(out)


def pdf_text(path: Path) -> str:
    from pypdf import PdfReader
    # 中文难免被拆字，统一挤掉空白再比对
    r = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in r.pages)


def squash(s: str) -> str:
    """去掉所有空白与常见的 PDF 拆字残留，做「宽松包含」比对。"""
    return re.sub(r"[\s　\u00a0]+", "", s or "")


def digits(s: str) -> str:
    """只留数字 —— 用来比「2005-01-14」和「2005.01.14」这种同值的不同写法。"""
    return re.sub(r"\D", "", s or "")


def core_fields(src: dict) -> dict:
    """从两处资料里抽出同一批核心字段，并抹平排版差异后再比。"""
    return {
        "姓名": squash(src.get("name", "")),
        "手机": re.sub(r"\D", "", src.get("phone", "")),
        "邮箱": squash(src.get("email", "")),
        "学校": squash(src.get("school", "")),
        "学院": squash(src.get("college", "")),
        "专业": squash(src.get("major", "")),
        "出生": digits(src.get("birth", "")),
        "GPA": squash(src.get("gpa", "")).replace("／", "/").upper(),
        "身高": digits(src.get("height", "")),
    }


def main() -> int:
    from ihub import tailor as tk

    kit = tk.kit()
    p = kit["profile"]
    truth = {
        "姓名": p["name"],
        "手机": p["phone"],
        "邮箱": p["email"],
        "学校": p["school"],
        "学院": p["college"],
        "专业": p["major"],
        "出生": p["birth"],
        "GPA": "3.47",
        "六级": "CET-6",
    }

    print("[1] 真值源自检")
    check("真值手机号是 11 位手机号", re.fullmatch(r"1[3-9]\d{9}", truth["手机"]) is not None, truth["手机"])
    check("真值邮箱带 @", "@" in truth["邮箱"], truth["邮箱"])
    check("出生日期是 2005.01.14", squash(truth["出生"]).replace(".", "") == "20050114", truth["出生"])

    print("[2] 逐份简历核对（docx / pdf / txt）")
    cvdir = ROOT / "简历材料" / "岗位定向简历"
    jobs = [("02_万能通用版_罗广睿_中国民航大学", ROOT / "简历材料")]
    for i, key in enumerate(tk.ORDER, 1):
        jobs.append((f"{i:02d}_{tk.file_of(key)}_罗广睿", cvdir))

    for stem, folder in jobs:
        dx, pd_, tx = folder / (stem + ".docx"), folder / (stem + ".pdf"), folder / (stem + ".txt")
        for f in (dx, pd_, tx):
            check(f"{stem} 存在 {f.suffix}", f.exists(), str(f))
        if not (dx.exists() and pd_.exists() and tx.exists()):
            continue

        bodies = {".docx": docx_text(dx), ".pdf": pdf_text(pd_),
                  ".txt": tx.read_text(encoding="utf-8")}
        for ext, body in bodies.items():
            sq = squash(body)
            label = f"{stem}{ext}"
            ok_missing = [k2 for k2, v in truth.items() if squash(v) not in sq]
            check(f"{label} 个人信息齐全", not ok_missing, f"缺：{ok_missing}")

            bad = [b for b in BANNED if squash(b) in sq]
            check(f"{label} 没有假号码 / 示例邮箱 / 旧残留", not bad, bad)

        check(f"{stem}.txt 是纯文本（无 md 符号）",
              not re.search(r"^\s*#|\*\*", tx.read_text(encoding="utf-8"), flags=re.M),
              "txt 里混进了 markdown")

    print("[3] pdf 全部是 1 页")
    from pypdf import PdfReader
    for stem, folder in jobs:
        pd_ = folder / (stem + ".pdf")
        if not pd_.exists():
            continue
        n = len(PdfReader(str(pd_)).pages)
        check(f"{stem}.pdf 正好 1 页", n == 1, n)

    print("[4] 简历内容确实覆盖三条技术主线")
    uni = squash((ROOT / "简历材料" / "02_万能通用版_罗广睿_中国民航大学.txt").read_text(encoding="utf-8"))
    for kw, why in (("STM32", "嵌入式"), ("MQTT", "物联网"), ("ROS2", "电气/自动化"),
                    ("LangChain", "AI 应用"), ("FreeRTOS", "嵌入式"), ("华为云", "IoT 上云")):
        check(f"通用版覆盖「{why}」关键词 {kw}", kw in uni)

    print("[5] 国企版是给烟草/中烟排的")
    soe_txt = None
    for stem, folder in jobs:
        if stem.startswith("04_"):
            soe_txt = squash((folder / (stem + ".txt")).read_text(encoding="utf-8"))
    if soe_txt:
        for kw in ("生源地云南大理", "回云南长期发展", "倒班", "服从组织安排"):
            check(f"国企版含关键句「{kw}」", squash(kw) in soe_txt)
    else:
        check("找到国企版", False)

    print("[6] 网申材料里的联系方式")
    qc = squash((ROOT / "简历材料" / "04_网申速填卡.txt").read_text(encoding="utf-8"))
    check("速填卡手机号正确", truth["手机"] in qc)
    check("速填卡邮箱正确", squash(truth["邮箱"]) in qc)
    wb = (ROOT / "简历材料" / "05_投递工作台.html").read_text(encoding="utf-8")
    check("工作台手机号正确", truth["手机"] in wb)
    check("工作台含学院", truth["学院"] in wb)
    lib = json.loads((ROOT / "简历材料" / "08_资料库.json").read_text(encoding="utf-8"))
    check("资料库手机号正确", lib["profile"]["phone"] == truth["手机"])
    check("资料库邮箱正确", lib["profile"]["email"] == truth["邮箱"])
    check("资料库是 9 套方向（1 通用 + 8 定向）", len(lib["directions"]) == 8 and "universal" in lib,
          len(lib.get("directions", {})))

    print("[7] 代码库里不许再出现占位个人信息")
    from ihub import profile as prof_mod
    d = prof_mod.DEFAULT
    check("profile.DEFAULT 的手机号为空", not d.get("phone"), d.get("phone"))
    check("profile.DEFAULT 的邮箱为空", not d.get("email"), d.get("email"))
    check("profile.DEFAULT 的姓名为空", not d.get("name"), d.get("name"))

    hits = []
    for base in (ROOT / "ihub", ROOT):
        for f in base.rglob("*.py"):
            parts = f.parts
            if "venv" in parts or "__pycache__" in parts or "tests" in parts:
                continue            # tests/ 里的 BANNED 清单本身就要写这些字符串
            try:
                raw = f.read_text(encoding="utf-8")
            except Exception:
                continue
            for ln in raw.splitlines():
                code = ln.split("#", 1)[0]           # 注释里记载事故原因不算违规
                # 只扫「个人信息类」黑名单：地名「潍坊」允许出现在数据源里，这里不拦
                for b in ("13800000000", "example@example.com", "13500135000"):
                    if b in code:
                        hits.append(f"{b} @ {f.relative_to(ROOT)}")
    check("源码里没有占位手机号 / 错号码 / 示例邮箱", not hits, hits)

    print("[8] 三处真值源必须一致（简历 与 网申助手 不能各写一套）")
    prof = json.loads((ROOT / "data" / "profile.json").read_text(encoding="utf-8"))
    a, b = core_fields(prof), core_fields(p)
    for k2, va in a.items():
        vb = b.get(k2, "")
        if not va:
            continue                              # profile.json 没填的不强求
        check(f"{k2}：profile.json 与 resume_kit 一致", va == vb, f"{va!r} vs {vb!r}")

    # 网申助手 / 网申书签里塞的资料，也必须跟简历是同一套
    for fn in ("网申助手.user.js", "网申书签.txt"):
        fp = ROOT / fn
        if not fp.exists():
            check(f"{fn} 存在", False, str(fp))
            continue
        body = fp.read_text(encoding="utf-8", errors="ignore")
        check(f"{fn} 里的手机号与简历一致",
              truth["手机"] in body.replace("-", "").replace(" ", ""),
              "网申脚本里还是别的号码")
        check(f"{fn} 里没有历史错号", "13500135000" not in body, "残留 13500135000")

    print(f"\n结果: {PASS} 通过, {FAIL} 失败")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
