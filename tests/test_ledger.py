# -*- coding: utf-8 -*-
"""投递台账（第 3 步重构）自测。

守三件事：
  1. 烟草「同一批次只能报 1 个单位 1 个岗位」必须能在**登记前**拦住（block）；
  2. 网申助手复制出来的 TSV / Excel 另存的 CSV 都能解析回记录；
  3. merge_plan 把「新增 / 只改状态 / 冲突」分得对，不会把冲突的悄悄放进去。

运行： venv\\Scripts\\python.exe tests/test_ledger.py
"""
from __future__ import annotations

import sys
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


def main() -> int:
    from ihub import ledger as L

    print("[1] 烟草口径识别")
    for name in ("云南省烟草专卖局", "云南中烟工业有限责任公司", "红云红河烟草集团",
                 "云南烟叶复烤有限公司", "昆明卷烟厂", "中国烟草总公司"):
        check(f"判为烟草：{name}", L.is_tobacco(name))
    for name in ("中国南方电网", "云南航空产业投资集团", "云南白药", "大理州人民政府"):
        check(f"不判为烟草：{name}", not L.is_tobacco(name))

    print("[2] 单位名/岗位名归一化比对")
    check("带括号注释的算同一家",
          L.same_unit("云南中烟工业有限责任公司（生产系统）", "云南中烟工业有限责任公司"))
    check("简称互相包含算同一家", L.same_unit("云南中烟", "云南中烟工业有限责任公司"))
    check("不同公司不算", not L.same_unit("云南中烟", "云南机场集团"))
    check("岗位名包含算同一个", L.same_job("设备运维岗", "设备运维岗（昆明）"))
    check("空值不算命中", not L.same_job("", "设备运维"))

    print("[3] 烟草：同批次只能 1 单位 1 岗 → 必须 block")
    existing = [{"company": "云南省烟草专卖局", "title": "信息中心技术岗", "stage": "已投"}]
    r = L.check_new("云南中烟工业有限责任公司", "设备运维岗", existing)
    check("已报省局后再报中烟 → block", r["level"] == "block", r)
    check("block 文案点明「取消资格」", "取消资格" in r["msg"], r["msg"][:60])
    check("block 会带上冲突的那条", len(r["hits"]) == 1)

    r2 = L.check_new("云南省烟草专卖局", "信息中心技术岗", existing)
    check("同一单位同一岗位再登一次 → block", r2["level"] == "block", r2)

    r3 = L.check_new("云南省烟草专卖局", "另一个技术岗", existing)
    check("同一单位换岗位也 block（1 单位 1 岗）", r3["level"] == "block", r3)

    print("[4] 前一条已放弃（未通过）时，允许改报")
    abandoned = [{"company": "云南省烟草专卖局", "title": "信息中心技术岗", "stage": "未通过"}]
    r4 = L.check_new("云南中烟工业有限责任公司", "设备运维岗", abandoned)
    check("上一条「未通过」不再占名额 → ok", r4["level"] == "ok", r4)
    r5 = L.check_new("云南省烟草专卖局", "信息中心技术岗", abandoned)
    check("同岗位重登但已「未通过」→ 不拦（属于重新报名）", r5["level"] != "block", r5)

    print("[5] 非烟草：同名公司同岗位 → warn，不 block")
    ex2 = [{"company": "云南航空产业投资集团", "title": "信息化岗", "stage": "已投"}]
    r6 = L.check_new("云南航空产业投资集团", "信息化岗", ex2)
    check("重复登记非烟草岗位 → warn", r6["level"] == "warn", r6)
    r7 = L.check_new("云南航空产业投资集团", "弱电工程师", ex2)
    check("同公司不同岗位 → ok", r7["level"] == "ok", r7)
    r8 = L.check_new("云南白药", "设备工程", ex2)
    check("完全不同公司 → ok", r8["level"] == "ok", r8)
    r9 = L.check_new("随便一家", "岗位", [])
    check("空台账 → ok", r9["level"] == "ok", r9)

    print("[6] 解析网申助手复制的 TSV")
    tsv = L.to_tsv([{"company": "云南中烟", "title": "设备运维", "city": "昆明",
                     "stage": "已投", "applied_at": "2026-09-16",
                     "url": "https://x/apply", "note": "网申助手记录"}])
    check("导出有表头", tsv.splitlines()[0] == "公司\t岗位\t城市\t状态\t投递日期\t链接\t备注")
    rows = L.parse_ledger_text(tsv)
    check("解析回 1 条", len(rows) == 1, rows)
    check("字段都对", rows[0]["company"] == "云南中烟" and rows[0]["stage"] == "已投"
          and rows[0]["url"] == "https://x/apply", rows[0])

    print("[7] 解析 Excel / 飞书另存的 CSV（带引号、逗号分隔）")
    csv = '公司,岗位,城市,状态,投递日期,链接,备注\n"云南中烟工业有限责任公司","设备运维,设备","昆明","已投",2026-09-16,https://x,\n'
    rows2 = L.parse_ledger_text(csv)
    check("CSV 能解析", len(rows2) == 1, rows2)
    check("带逗号的引号字段没被切坏", rows2[0]["title"] == "设备运维,设备", rows2[0])

    print("[8] 手打的一行一条（没有表头）")
    rows3 = L.parse_ledger_text("云南机场集团 | 信息化岗 | 昆明 | 已投\n云南白药 设备工程 昆明")
    check("解析 2 条", len(rows3) == 2, rows3)
    check("第一条字段对", rows3[0]["company"] == "云南机场集团" and rows3[0]["stage"] == "已投", rows3[0])
    check("第二条缺状态时默认「已投」（网申场景）", rows3[1]["stage"] == "已投", rows3[1])

    print("[9] 空输入 / 脏输入不炸")
    check("空字符串 → []", L.parse_ledger_text("") == [])
    check("只有表头 → []", L.parse_ledger_text("公司\t岗位\t城市\t状态") == [])
    check("全是空白行 → []", L.parse_ledger_text("\n\n   \n") == [])
    check("缺公司名的行被丢掉", L.parse_ledger_text("公司\t岗位\n\t设备运维\n") == [])

    print("[10] merge_plan 分堆：冲突不能悄悄进「新增」")
    plan = L.merge_plan(
        L.parse_ledger_text(
            "公司\t岗位\t城市\t状态\t投递日期\n"
            "云南中烟工业有限责任公司\t设备运维\t昆明\t已投\t2026-09-16\n"      # 冲突（已有省局）
            "云南航空产业投资集团\t信息化岗\t昆明\t笔试\t2026-09-17\n"          # 只改状态
            "云南白药\t设备工程\t昆明\t已投\t2026-09-17\n"),                     # 新增
        [{"company": "云南省烟草专卖局", "title": "信息中心技术岗", "stage": "已投"},
         {"company": "云南航空产业投资集团", "title": "信息化岗", "stage": "已投"}])
    check("1 条新增", len(plan["new"]) == 1, plan["new"])
    check("1 条只改状态", len(plan["update"]) == 1, [x[0] for x in plan["update"]])
    check("1 条冲突被拦住", len(plan["conflict"]) == 1, [x[0] for x in plan["conflict"]])
    check("新增的那条是云南白药", plan["new"][0]["company"] == "云南白药", plan["new"])
    check("改状态的那条是机场集团", plan["update"][0][0]["company"] == "云南航空产业投资集团")
    check("冲突的那条是云南中烟", plan["conflict"][0][0]["company"] == "云南中烟工业有限责任公司")
    check("summary_line 能读", "冲突拦截 1 条" in L.summary_line(plan), L.summary_line(plan))

    print("[11] 烟草名额占用统计")
    ex = [{"company": "云南中烟", "title": "a", "stage": "已投"},
          {"company": "云南省烟草专卖局", "title": "b", "stage": "未通过"},
          {"company": "云南机场集团", "title": "c", "stage": "已投"}]
    tob = L.tobacco_rows(ex)
    check("烟草占名额 2 条（未通过也列出，供人工确认）", len(tob) == 2, [r["company"] for r in tob])
    r10 = L.check_new("云南省烟草专卖局", "新岗位", ex)
    check("有「已投」的烟草记录时，再登记 → block", r10["level"] == "block", r10)

    print(f"\n结果: {PASS} 通过, {FAIL} 失败")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
