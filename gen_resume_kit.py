# -*- coding: utf-8 -*-
"""一键重新生成全部简历材料（改完 data/resume_kit.json 后跑这个）。

用法：
    venv\\Scripts\\python.exe gen_resume_kit.py            # 全量生成
    venv\\Scripts\\python.exe gen_resume_kit.py 简历材料      # 只生成指定部分

产出（都在 简历材料/ 目录）：
    02_万能通用版_罗广睿_中国民航大学.pdf / .docx
    岗位定向简历/01..08_xxx_罗广睿.pdf / .docx     （8 个方向各一份）
    04_网申速填卡.txt
    05_投递工作台.html                              （粘贴 JD 自动生成定向简历与文案）
    01_简历诊断与优化报告.docx / .md
    00_先读我_使用说明.docx / .md
    08_资料库.json                                  （结构化资料，可手改）
网申助手脚本另由 `python -m ihub.autofill` 生成到项目根目录（run_all 里已包含）。
"""
from __future__ import annotations

import json
import os
import shutil
import sys

from ihub import config, tailor
from ihub import md2docx

ROOT = config.PROJECT_ROOT
OUT = os.path.join(ROOT, "简历材料")
CV = os.path.join(OUT, "岗位定向简历")
SRC = os.path.join(OUT, "源文件")


def _log(*a):
    print(*a)


def gen_resumes():
    made = []
    jobs = [("02_万能通用版_罗广睿_中国民航大学", "universal", OUT)]
    for i, key in enumerate(tailor.ORDER, 1):
        jobs.append((f"{i:02d}_{tailor.file_of(key)}_罗广睿", key, CV))
    for name, key, folder in jobs:
        dx = os.path.join(folder, name + ".docx")
        tailor.resume_docx(key, dx, None)
        made.append(dx)
        pdf = os.path.join(folder, name + ".pdf")
        try:
            tailor.build_pdf(key, pdf, None)
            made.append(pdf)
        except Exception as e:                       # 缺 reportlab / 字体时降级
            _log(f"  ! {name} 未生成 PDF（{e}），docx 已就绪")
    return made


def gen_workbench():
    tpl_path = os.path.join(ROOT, "ihub", "workbench.tpl.html")
    tpl = open(tpl_path, encoding="utf-8").read()
    payload = json.dumps(tailor.kit(), ensure_ascii=False, indent=1)
    html = tpl.replace("/*__DATA__*/{}", payload)
    p = os.path.join(OUT, "05_投递工作台.html")
    open(p, "w", encoding="utf-8").write(html)
    return p


def gen_quickcard():
    p = os.path.join(OUT, "04_网申速填卡.txt")
    open(p, "w", encoding="utf-8").write(tailor.quickcard())
    return p


def gen_library():
    p = os.path.join(OUT, "08_资料库.json")
    open(p, "w", encoding="utf-8").write(json.dumps(tailor.kit(), ensure_ascii=False, indent=1))
    return p


def gen_docs():
    made = []
    for src_name, out_name in (("诊断报告.md", "01_简历诊断与优化报告"),
                               ("使用说明.md", "00_先读我_使用说明")):
        s = os.path.join(SRC, src_name)
        if not os.path.exists(s):
            continue
        md = os.path.join(OUT, out_name + ".md")
        shutil.copyfile(s, md)
        made.append(md)
        dx = os.path.join(OUT, out_name + ".docx")
        try:
            md2docx.build(s, dx)
            made.append(dx)
        except Exception as e:
            _log(f"  ! {out_name}.docx 生成失败：{e}")
    return made


def main() -> int:
    os.makedirs(CV, exist_ok=True)
    os.makedirs(SRC, exist_ok=True)

    _log("[1/5] 生成简历（万能通用版 + 8 个岗位方向）…")
    files = gen_resumes()
    for f in files:
        _log(f"      {os.path.getsize(f):>8}  {os.path.relpath(f, ROOT)}")

    _log("[2/5] 生成投递工作台网页…")
    _log("      " + os.path.relpath(gen_workbench(), ROOT))
    _log("[3/5] 生成网申速填卡…")
    _log("      " + os.path.relpath(gen_quickcard(), ROOT))
    _log("[4/5] 生成资料库 JSON…")
    _log("      " + os.path.relpath(gen_library(), ROOT))
    _log("[5/5] 生成诊断报告 / 使用说明…")
    for f in gen_docs():
        _log("      " + os.path.relpath(f, ROOT))

    _log("\n完成。网申助手脚本请跑：venv\\Scripts\\python.exe -m ihub.autofill")
    _log("全部材料在：" + OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
