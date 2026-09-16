# -*- coding: utf-8 -*-
"""渠道链接体检 —— 跑一遍项目里所有会给用户点的链接，输出分级报告。

用法：
    venv\\Scripts\\python.exe run_linkcheck.py            # 全量体检（约 1~2 分钟）
    venv\\Scripts\\python.exe run_linkcheck.py --only ynairport   # 只查某几个站
    venv\\Scripts\\python.exe run_linkcheck.py --report-only      # 不联网，用上次结果重出报告

产物：
    data/link_health.json    机器可读（网页端也在读它）
    链接体检报告.md           人工看，A/B/C/D 分级 + 判定依据
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from datetime import datetime                                  # noqa: E402
from ihub import linkcheck as lc                               # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=None, help="只体检 URL 里含这些关键字的链接")
    ap.add_argument("--report-only", action="store_true", help="不联网，用上次结果重出报告")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()

    if a.report_only:
        results = lc.load_saved()
        stamp = ""
    else:
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        print(f"开始体检…（{len(lc.collect_targets())} 条待检链接）")
        results = lc.run(workers=a.workers, only=a.only)
        lc.save(results)

    s = lc.summary(results)
    print(f"\n受检 {s['total']} 条：" + " ｜ ".join(f"{g} {s[g]}" for g in lc.GRADE_ORDER))

    for g in lc.GRADE_ORDER:
        rows = [r for r in results if r["grade"] == g]
        if not rows:
            continue
        print(f"\n--- {g} 级（{len(rows)}）---")
        for r in rows:
            print(f"  [{g}] {r['label'][:22]:<24} {r['url'][:64]}")
            print(f"        {r['reason']}")

    out = os.path.join(ROOT, "链接体检报告.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write(lc.report_md(results, stamp))
    print(f"\n报告已写入：{out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
