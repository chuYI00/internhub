# -*- coding: utf-8 -*-
"""生成备考方案（第 4 步重构）—— 命令行入口，不打开网页也能出方案。

用法：
    venv\\Scripts\\python.exe run_studyplan.py                          # 云南中烟 · 默认考试日 · 6h/天
    venv\\Scripts\\python.exe run_studyplan.py --list                    # 看内置目标
    venv\\Scripts\\python.exe run_studyplan.py --target 云南省烟草专卖局 --role 信息技术 --hours 4
    venv\\Scripts\\python.exe run_studyplan.py --target 云南省交通投资建设集团 --role 信息化 --date 2026-11-20

产物：
    备考冲刺资料/备考方案_<单位>.md
    备考冲刺资料/备考方案_<单位>.docx   （Word 生成失败时只给 md，不影响使用）
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from ihub import studyplan as sp                                  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="按目标单位生成备考方案")
    ap.add_argument("--list", action="store_true", help="列出内置目标单位")
    ap.add_argument("--target", default="云南中烟", help="目标单位（可填别名，也可填自己的单位名）")
    ap.add_argument("--role", default="", help="目标岗位，决定专业知识考哪一套")
    ap.add_argument("--date", default="", help="考试日期 YYYY-MM-DD（不填按往年节奏给默认值）")
    ap.add_argument("--hours", type=int, default=6, help="每天可学小时数（默认 6）")
    ap.add_argument("--no-docx", action="store_true", help="只要 Markdown，不生成 Word")
    a = ap.parse_args()

    if a.list:
        print("内置目标单位（也可以直接填别名，如「云南烟草」「红塔」「大理机场」）：")
        for t in sp.targets():
            print("  ·", t)
        return 0

    short = sp.profile_of(a.target)["short"]
    edate = a.date or sp.default_exam_date(short)
    if not a.date:
        print(f"（没给日期，按往年节奏默认 {edate}，可用 --date 改）")

    plan = sp.generate(a.target, role=a.role, exam_date=edate, hours=a.hours)
    md_path = sp.save_markdown(plan)
    print(f"目标档案：{plan['short']}　岗位方向：{plan['role_key']}")
    print(f"剩余 {plan['days_left']} 天　每天 {plan['hours_per_day']}h　"
          f"总可用 {plan['total_hours']}h　课表实际 {plan['schedule_total']}h/天")
    print(f"Markdown：{md_path}")
    if not a.no_docx:
        docx = sp.save_docx(plan, md_path)
        print(f"Word    ：{docx}" if docx else "Word    ：生成失败（缺 python-docx？Markdown 已可用）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
