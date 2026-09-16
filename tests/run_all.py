# -*- coding: utf-8 -*-
"""一键跑完所有自测（改代码后先跑这个，别手点页面才发现坏）。

用法：
    venv\\Scripts\\python.exe tests\\run_all.py
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable


def run(cmd: list[str], label: str) -> bool:
    print(f"\n===== {label} =====")
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    r = subprocess.run(cmd, cwd=str(ROOT), env=env,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    lines = out.splitlines()
    print("\n".join(lines[-12:]) if lines else "(无输出)")
    ok = r.returncode == 0
    print(f"-> {label}: {'通过' if ok else '**失败**'}")
    return ok


def main() -> int:
    results: dict[str, bool] = {}

    print("\n===== 重新生成采集/网申脚本（书签与油猴脚本同源） =====")
    for mod, label in (("ihub.collector", "采集助手 + 采集书签"), ("ihub.autofill", "网申助手 + 网申书签")):
        r = subprocess.run([PY, "-m", mod], cwd=str(ROOT),
                           env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        out = ((r.stdout or "") + (r.stderr or "")).strip()
        print(f"[{label}] " + (out or "(无输出)"))
        results[f"生成 {label}"] = r.returncode == 0

    results["采集助手（油猴版）"] = run(
        ["node", "tests/collector_dom_test.js"], "采集助手 .user.js")
    results["网申助手（油猴版）"] = run(
        ["node", "tests/autofill_dom_test.js"], "网申助手 .user.js")
    results["采集书签（免插件版）"] = run(
        ["node", "tests/bookmarklet_test.js"], "采集书签 采集书签.txt")
    results["CSV 导入链路"] = run(
        [PY, "tests/test_import_csv.py"], "CSV 导入 → 入库")
    results["网页端冒烟（9 个页签 + 广投按钮）"] = run(
        [PY, "tests/test_app_smoke.py"], "Streamlit 无头渲染")

    print("\n================ 汇总 ================")
    for k, v in results.items():
        print(f"  {'[OK]  ' if v else '[FAIL]'} {k}")
    bad = [k for k, v in results.items() if not v]
    print("\n全部通过 ✅" if not bad else f"\n有 {len(bad)} 项失败 ❌：{', '.join(bad)}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
