# -*- coding: utf-8 -*-
"""🍃 烟草招聘监控 —— 命令行一次性扫描。

用法（在项目根目录）：
    venv\\Scripts\\python.exe run_tobacco_watch.py             # 扫一遍，只在有新增时报出来
    venv\\Scripts\\python.exe run_tobacco_watch.py --all       # 连"全部公告"一起打印
    venv\\Scripts\\python.exe run_tobacco_watch.py --pages 3   # 多翻几页
    venv\\Scripts\\python.exe run_tobacco_watch.py --json      # 输出 JSON（给定时任务/自动化用）
    venv\\Scripts\\python.exe run_tobacco_watch.py --reset     # 清空"已见"记录（重新全量报一次）

设计要点：**只有新增才值得打扰你**。第一次跑会把当前已有公告全部收进"已见"，
之后每次只报增量 —— 所以第一次跑你可能看到几十条，那是正常的（那是历史公告）。
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ihub import tobacco as T  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="烟草招聘监控（国家烟草专卖局人才招聘专栏）")
    ap.add_argument("--pages", type=int, default=2, help="翻几页列表（每页 20 条）")
    ap.add_argument("--detail", type=int, default=8, help="对前 N 条新公告抓详情取报名窗口")
    ap.add_argument("--all", action="store_true", help="连全部公告一起打印")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--only-recruit", action="store_true", help="只有招聘公告才算新增（过滤公示）")
    ap.add_argument("--tech-only", action="store_true",
                    help="只看技术/管理类岗位（滤掉一线操作岗；你的定位是偏技术非一线）")
    ap.add_argument("--reset", action="store_true", help="清空已见记录")
    args = ap.parse_args()

    if args.reset:
        try:
            os.remove(T.STATE_PATH)
            print("已清空已见记录：" + T.STATE_PATH)
        except FileNotFoundError:
            print("本来就没有已见记录。")

    res = T.scan(pages=args.pages, detail_top=args.detail,
                 only_recruit=args.only_recruit, tech_only=args.tech_only)

    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
        return 0

    new = T.by_priority(res["new"])
    if not new:
        print(f'✅ 无新增（{res["checked_at"]}，累计已见 {res["total_seen"]} 条）')
    else:
        print(f'🍃 发现 {len(new)} 条新公告！（{res["checked_at"]}）')
        print("=" * 62)
        for it in new:
            print(f'{T.stars(it["priority"])} [{it["kind"]}] {it["title"]}')
            if it.get("role"):
                print(f'    岗位取向：{it["role"]}　{it.get("role_note", "")}')
            print(f'    {it["link"]}')
            if it.get("apply_from") or it.get("apply_to"):
                seg = (f'    报名窗口：{it.get("apply_from") or "?"} ~ {it.get("apply_to") or "?"}'
                       f'（{it.get("open_days") or "?"} 天）')
                if it.get("days_left") is not None:
                    d = it["days_left"]
                    seg += "　⏰ 还剩 %d 天" % d if d >= 0 else "　（已结束）"
                print(seg)
            if it.get("apply_platform"):
                print(f'    报名平台：{it["apply_platform"]}')
            if it.get("quota_note"):
                print(f'    {it["quota_note"]}')
            print()

    urgent = T.urgent(T.by_priority(res["all"]))
    if urgent:
        print("⏰ 正在报名、10 天内截止的：")
        for it in urgent:
            print(f'   [{it.get("days_left")} 天] {it["title"][:46]}')
            print(f'          {it["link"]}')
        print()

    if args.all:
        print(T.as_text(res))

    print("岗位取向：✅技术/管理类=优先投　⛔一线/操作类=你不投，仅参考　⚠️混合=进公告看岗位表")
    print("⚠️ 烟草铁律：同批次只能报 1 个单位 1 个岗位，重复投递取消资格；"
          "窗口通常只有 7~10 天，看到公告当天就动手。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
