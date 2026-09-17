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
    results["网申助手·ATS 兼容（北森/antd/element）"] = run(
        ["node", "tests/autofill_ats_test.js"], "企业自有网申系统（自绘下拉/卡片单选）")
    results["网申助手（油猴版）"] = run(
        ["node", "tests/autofill_dom_test.js"], "网申助手 .user.js")
    results["网申助手 v5（70 字段 / 三级识别 / 字段学习）"] = run(
        ["node", "tests/autofill_v5_test.js"], "网申助手 v5：国企特色字段 + 填充报告 + 教一次会记")
    results["网申助手 · 真实浏览器验收（北森/Moka/国企三种结构）"] = run(
        [PY, "tests/autofill_browser_test.py"], "真实 Chrome/Edge 跑三种网申页面，看填充率与识别率")
    results["采集书签（免插件版）"] = run(
        ["node", "tests/bookmarklet_test.js"], "采集书签 采集书签.txt")
    results["采集链路（跳转壳解码 + 数据源并集 + 官网匹配）"] = run(
        [PY, "tests/test_weblist.py"], "采集：官方投递入口/公司名/数据源")
    results["🍃 烟草监控（报名窗口 / 新增比对 / 排序）"] = run(
        [PY, "tests/test_tobacco.py"], "烟草监控：只报增量 + 报名窗口倒计时")
    results["🔍 链接体检（伪直达识别 / 分级 / 官方字段无污染）"] = run(
        [PY, "tests/test_linkcheck.py"], "链接体检：A/P/B/C/D 分级 + 砍伪直达")
    results["📮 投递台账（烟草 1 单位 1 岗拦截 / 粘贴解析）"] = run(
        [PY, "tests/test_ledger.py"], "投递台账：登记前拦截 + 网申助手回传解析")
    results["📥 导入向导（4 通道 / 乱列名映射 / 抓包解码 / 去重）"] = run(
        [PY, "tests/test_wizard.py"], "导入向导：解析 → 映射 → 入库 → 去重")
    results["📚 备考方案生成器（倒推阶段 / 必背清单 / 导出）"] = run(
        [PY, "tests/test_studyplan.py"], "备考方案：按考试日倒推 + 分目标出方案")
    results["CSV 导入链路"] = run(
        [PY, "tests/test_import_csv.py"], "CSV 导入 → 入库")
    results["🧭 岗位列表（排序 / 城市多选 / 报名中 / 发布时间兜底 / 临期标红）"] = run(
        [PY, "tests/test_joblist.py"], "岗位页：排序筛选 + 发布时间不许为空")
    results["📒 手机备考手册（微课指引 / 三级标签 / 模式 A·B / 个人总结）"] = run(
        [PY, "tests/test_study_card.py"], "备考卡片网页：真浏览器跑一遍，确认分层与原有功能都没坏")
    results["网页端冒烟（4 个页签 + 页签对齐 + 广投按钮）"] = run(
        [PY, "tests/test_app_smoke.py"], "Streamlit 无头渲染")
    results["简历定制链路"] = run(
        [PY, "tests/test_tailor.py"], "简历定制（方向识别 + 单页排版 + 网页页签）")

    print("\n================ 汇总 ================")
    for k, v in results.items():
        print(f"  {'[OK]  ' if v else '[FAIL]'} {k}")
    bad = [k for k, v in results.items() if not v]
    print("\n全部通过 ✅" if not bad else f"\n有 {len(bad)} 项失败 ❌：{', '.join(bad)}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
