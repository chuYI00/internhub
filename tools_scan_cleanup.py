# -*- coding: utf-8 -*-
"""生成《待清理清单.md》—— 只列候选、不删任何文件。

对每条候选给出：路径 | 是什么 | 为什么候选 | 最后被谁引用（真 grep 出来的）。
确认后才删，删之前必须先 commit。
"""
from __future__ import annotations

import os
import re
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent          # intern_tool/
OUT = ROOT / "待清理清单.md"
# 这两个文件里必然写着候选文件名（就是它们在做统计），不能算「被引用」
SELF_FILES = {"tools_scan_cleanup.py", "待清理清单.md"}

SKIP_DIRS = {"venv", ".git", "__pycache__", "node_modules", ".workbuddy", "backup", "mobile"}
TEXT_EXT = {".py", ".md", ".txt", ".js", ".json", ".csv", ".bat", ".html", ".yaml", ".yml"}


def rel(p: Path) -> str:
    try:
        return str(p.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(p)


def load_text_files():
    files = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            p = Path(dirpath) / fn
            if p.suffix.lower() in TEXT_EXT and p.stat().st_size < 3_000_000:
                files.append(p)
    return files


def build_index(files):
    idx = {}
    for p in files:
        try:
            idx[p] = p.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            idx[p] = []
    return idx


def who_references(p: Path, files, index):
    pat = re.compile(re.escape(p.name))
    hits = []
    for f in files:
        if f == p or rel(f) in SELF_FILES:
            continue
        for i, ln in enumerate(index.get(f) or [], 1):
            if pat.search(ln):
                hits.append((rel(f), i, ln.strip().replace("|", "\\|")[:60]))
                break
    return hits[:3]


def kb(size: int) -> str:
    return f"{size/1024:.0f} KB" if size < 1024 * 1024 else f"{size/1048576:.1f} MB"


def _git() -> str:
    """找到真能跑起来的 git（本机 shutil.which 会返回一个跑不起来的 shim，所以要试运行）。"""
    import shutil
    cands = [shutil.which("git") or ""] + [
        r"C:\Users\luo\.workbuddy\binaries\PortableGit\versions\1.2.0\bin\git.exe",
        r"C:\Users\luo\.workbuddy\binaries\PortableGit\versions\1.2.0\cmd\git.exe",
        r"C:\Program Files\Git\bin\git.exe",
        r"C:\Program Files\Git\cmd\git.exe",
    ]
    for c in cands:
        if not c:
            continue
        try:
            r = subprocess.run([c, "--version"], capture_output=True, timeout=15)
            if r.returncode == 0:
                return c
        except Exception:
            continue
    return "git"


def git_tracked(name: str) -> str:
    from ihub import config as _cfg
    g = _git()
    try:
        r = subprocess.run([g, "ls-files", "--error-unmatch", name], cwd=str(_cfg.PROJECT_ROOT),
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode == 0:
            return "已入库"
        r2 = subprocess.run([g, "rev-parse", "--is-inside-work-tree"], cwd=str(_cfg.PROJECT_ROOT),
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r2.returncode != 0:
            return "非 Git 仓库"
    except Exception:
        return "?"
    return "未入库"


DESCRIBE = {
    "重构指令-给AI执行.md": "v1 任务书（12→4 页签那一轮）",
    "重构指令v2-可用性与美观-给AI执行.md": "v2 任务书（导入向导收敛）",
    "重构指令v3-网申主攻-给AI执行.md": "v3 任务书（本轮五任务）",
    "解码飞书表格.py": "把飞书导出 CSV 解码成岗位表的临时脚本",
    "飞书只读表格导出实操指南.md": "配套操作说明（怎么从飞书里导表）",
    "data/飞书岗位导出.csv": "那次导出的数据快照",
    "导入教程.md": "早期 CSV 导入教程（已被页内向导取代）",
    "备考冲刺资料/云南烟草冲刺备考资料.md": "早期备考资料，已被《2027届备考作战方案》取代",
    "备考冲刺资料/云南烟草冲刺备考资料.docx": "上面那份的 Word 版",
}


def describe(name: str) -> str:
    if name in DESCRIBE:
        return DESCRIBE[name]
    suf = Path(name).suffix.lower()
    return {".bak": "旧版本备份", ".csv": "数据快照", ".json": "数据文件",
            ".docx": "Word 成品", ".md": "Markdown 文档", ".py": "Python 脚本",
            ".txt": "文本清单"}.get(suf, "文件")


ROOT_FILES = {
    "app.py": "主网页（4 页签）",
    "gen_resume_kit.py": "一键重生成简历材料 / 备考文档 / 清单",
    "md2docx.py": "md → docx 小工具",
    "run_crawl.py": "命令行抓取",
    "run_import.py": "CSV 导入",
    "run_linkcheck.py": "链接体检",
    "run_parse_html.py": "本地 HTML 解析",
    "run_studyplan.py": "备考方案生成",
    "run_tobacco_watch.py": "烟草监控（自动化在跑）",
    "scheduler.py": "定时调度",
    "sources.json": "**权威**数据源（根目录这份随 Git 管）",
    "网申助手.user.js": "网申助手 v5（由 ihub/autofill.py 生成）",
    "网申书签.txt": "网申助手书签版",
    "网申助手使用说明.md": "3 步上手说明",
    "采集助手.user.js": "采集助手油猴脚本",
    "采集书签.txt": "采集书签",
    "采集书签说明.md": "采集书签安装说明",
    "链接体检报告.md": "最近一次链接体检产物",
    "插件安装说明.md": "Tampermonkey 安装说明",
    "示例_导入模板.csv": "导入向导用的示例模板",
    "秋招_潍坊昆明大理.csv": "早期导入的一批秋招岗位",
    "脚本自检.html": "脚本自检页",
    "README.md": "项目说明",
    "LICENSE": "开源协议",
    "requirements.txt": "依赖清单",
}


def main() -> int:
    files = load_text_files()
    index = build_index(files)

    groups = []

    # A. 旧版指令文档
    g = ("A. 旧版重构指令（任务书，做完就该归档）", [
        "重构指令-给AI执行.md",
        "重构指令v2-可用性与美观-给AI执行.md",
        "重构指令v3-网申主攻-给AI执行.md",
    ], "这三份是写给我（AI）的任务书，**代码里没有任何一行读它们**。留在根目录只是占地方。"
        "但删了就没法回溯「当时为什么这么改」—— 建议**移动**到 `docs/指令归档/`，别直接删。")
    groups.append(g)

    # B. 飞书一次性通道
    g = ("B. 飞书那条一次性通道（已换成通用导入向导）", [
        "解码飞书表格.py",
        "飞书只读表格导出实操指南.md",
        "data/飞书岗位导出.csv",
        "导入教程.md",
    ], "当时为了导一份飞书只读表临时写的脚本 + 说明。现在岗位页的「📥 导入向导」"
        "能吃各种表格（上传 / 粘贴 / 抓包 / OCR 四条通道），这条一次性通道可以退。")
    groups.append(g)

    # C. 备份
    baks = []
    bd = ROOT / "backup"
    if bd.is_dir():
        baks += [rel(p) for p in sorted(bd.iterdir()) if p.is_file()]
    baks += [rel(p) for p in sorted(ROOT.glob("*.bak"))]
    g = ("C. 备份文件（`.bak` / backup 目录）", baks,
         "手搓的旧版本备份。**代码不读它们**，纯历史保险 —— "
         "真要旧版，`git log` 里都有，不用在工作目录里堆着。")
    groups.append(g)

    # D. data/ 下无引用的 json/csv
    known = re.compile(r"(profile\.json|resume_kit\.json|sources\.json|official_urls\.json|"
                       r"link_health\.json|tobacco_seen\.json|study_checklist\.json|jobs\.db)", re.I)
    unreferenced = []
    dd = ROOT / "data"
    if dd.is_dir():
        for p in sorted(dd.iterdir()):
            if not p.is_file() or p.suffix.lower() not in (".json", ".csv"):
                continue
            if known.search(p.name):
                continue
            if not who_references(p, files, index):
                unreferenced.append(rel(p))
    g = ("D. `data/` 下没有任何代码引用的数据文件", unreferenced,
         "配置文件散在两处历史上坑过一次（`sources.json` 根目录和 `data/` 各一份，"
         "往 `data/` 里加的源永远不生效且零提示）。这里把**确实没人读**的挑出来。")
    groups.append(g)

    # E. 被取代的成品文档
    dup = []
    for cand in ("备考冲刺资料/云南烟草冲刺备考资料.md",
                 "备考冲刺资料/云南烟草冲刺备考资料.docx"):
        if (ROOT / cand).exists():
            dup.append(cand)
    g = ("E. 已被取代的成品文档", dup,
         "早期写的备考资料，内容已被《云南烟草2027届备考作战方案》完整覆盖，"
         "手机上那本《手机备考手册》也是从后者摘的。留着只会让你不确定该看哪份。")
    groups.append(g)

    md = []
    md.append("# 待清理清单（**只列候选，一个都没删**）\n\n")
    md.append(f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}"
              f"　|　扫描根目录：`{ROOT}`\n")
    md.append("> ⚠️ **本文件只是候选名单**。删哪几条你说了算；确认后**先 commit 再删**，"
              "删完跑一遍 `venv\\Scripts\\python.exe tests\\run_all.py`。\n\n")
    md.append("判据：拿不准就**移动**不删除 —— 下面每条都给了建议动作。\n")

    total_files = 0
    total_size = 0
    risky = []

    for title, items, why in groups:
        md.append(f"\n## {title}\n\n{why}\n\n")
        if not items:
            md.append("_（这一类没有候选，干净）_\n")
            continue
        md.append("| 路径 | 大小 | 是什么 | 最后被谁引用（grep） | Git | 建议动作 |\n")
        md.append("|---|---|---|---|---|---|\n")
        for name in items:
            p = ROOT / name
            if not p.exists():
                continue
            size = p.stat().st_size
            total_files += 1
            total_size += size
            hits = who_references(p, files, index)
            if hits:
                ref = "<br>".join(f"`{r}:{i}` {ln}" for r, i, ln in hits)
                advice = "⚠️ **还有引用，先别动**"
                risky.append(name)
            else:
                ref = "**无任何引用**"
                if title.startswith("A."):
                    advice = "移到 `docs/指令归档/`（别删）"
                elif name.endswith(".bak") or "/backup/" in name:
                    advice = "可直接删（旧版在 Git 历史里）"
                else:
                    advice = "确认后可删"
            md.append(f"| `{name}` | {kb(size)} | {describe(name)} | {ref} | "
                      f"{git_tracked(name)} | {advice} |\n")

    md.append("\n---\n\n## 附：根目录在用的文件（帮你核对没漏网）\n\n")
    md.append("| 路径 | 大小 | 用途 |\n|---|---|---|\n")
    for name, desc in ROOT_FILES.items():
        p = ROOT / name
        if p.exists():
            md.append(f"| `{name}` | {kb(p.stat().st_size)} | {desc} |\n")

    md.append(f"\n---\n\n**候选合计 {total_files} 个文件，约 {kb(total_size)}。**\n")
    if risky:
        md.append(f"\n⚠️ 其中 **{len(risky)} 条还有代码/文档在引用**，动了会坏："
                  f"{'、'.join('`%s`' % x for x in risky)}\n")
    md.append("\n### 删除前三步（别跳）\n")
    md.append("1. `git status` 确认工作区干净，或先把改动 commit；\n")
    md.append("2. 一次只删一类，删完立刻跑 `venv\\Scripts\\python.exe tests\\run_all.py`；\n")
    md.append("3. 全绿再删下一类。哪类挂了，用上一个 commit 恢复。\n")

    OUT.write_text("".join(md), encoding="utf-8")
    print(f"已生成：{OUT}")
    print(f"候选 {total_files} 个文件，约 {kb(total_size)}")
    if risky:
        print(f"其中还有引用的（别动）：{risky}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
