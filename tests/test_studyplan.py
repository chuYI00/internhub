# -*- coding: utf-8 -*-
"""备考方案生成器（第 4 步重构）自测。

要点：
  · 剩余天数能按考试日倒推，阶段划分随天数变形（7 天 / 21 天 / 45 天 / 90 天 四个档）
  · 岗位类型能落到三套专业知识清单之一（电气自动化 / 机械 / 计算机信息）
  · 生成的方案必须是「完整的」：考情分析、重点排序（含「该放弃什么」）、
    分阶段计划、每日课表、必背清单、资料来源 —— 一样不能少
  · 云南烟草那份冲刺模板要有真正能背的行业常识（架构 / 两烟大省 / 专卖法要点 / 专业分岗）

运行： venv\\Scripts\\python.exe tests/test_studyplan.py
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
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
    from ihub import studyplan as sp

    print("[1] 目标档案")
    ts = sp.targets()
    check("内置目标 ≥6 个", len(ts) >= 6, ts)
    for kw in ("云南中烟", "云南省烟草专卖局", "南方电网", "航空产业投资", "银行", "央国企"):
        check(f"含目标「{kw}」", any(kw in t for t in ts), ts)
    check("别名能匹配（「云南烟草专卖局」→ 省局档案）",
          sp.profile_of("云南烟草专卖局")["short"] == "云南省烟草专卖局",
          sp.profile_of("云南烟草专卖局")["short"])
    check("别名能匹配（「红塔集团」→ 中烟档案）", sp.profile_of("红塔集团")["short"] == "云南中烟")
    check("未知单位兜底到通用档案", sp.profile_of("某某科技有限公司")["short"] == "央国企")
    # 光打「云南烟草」这种最常见的叫法也必须落到烟草，不能掉进通用兜底
    check("「云南烟草」→ 烟草档案（不是央国企兜底）",
          sp.profile_of("云南烟草")["short"] in ("云南省烟草专卖局", "云南中烟"),
          sp.profile_of("云南烟草")["short"])
    check("「云南中烟」→ 中烟档案", sp.profile_of("云南中烟")["short"] == "云南中烟")
    check("「大理机场」→ 航产投档案", sp.profile_of("大理机场")["short"] == "云南航产投")
    check("「工商银行大理分行」→ 银行档案", sp.profile_of("工商银行大理分行")["short"] == "银行")
    # 最长别名优先：同时含两个关键词时，别配到较短的那个
    check("最长别名优先（「云南烟草专卖局」不因含「烟草」而错配）",
          sp.profile_of("云南烟草专卖局")["short"] == "云南省烟草专卖局",
          sp.profile_of("云南烟草专卖局")["short"])

    print("[2] 岗位 → 专业知识清单")
    check("电气 → 电气/自动化", sp.role_key_of("云南中烟（生产系统）", "电气工程师") == "电气/自动化")
    check("自动化 → 电气/自动化", sp.role_key_of("云南中烟（生产系统）", "设备自动化") == "电气/自动化")
    check("物联网 → 计算机/信息", sp.role_key_of("云南中烟（生产系统）", "物联网工程") == "计算机/信息")
    check("信息中心 → 计算机/信息", sp.role_key_of("云南省烟草专卖局（商业系统）", "信息中心技术岗")
          == "计算机/信息")
    check("空岗位也能落一套", sp.role_key_of("通用·央国企（不限企业）", "") in ("计算机/信息", "电气/自动化"))
    check("电网有自己的一套（信息通信类）", sp.role_key_of("电网·南方电网（云南电网）", "信息通信")
          == "信息通信类")

    print("[3] 剩余天数倒推")
    today = date(2026, 9, 16)
    check("算得对（9/16 → 12/6 是 81 天）", sp.days_left("2026-12-06", today) == 81,
          sp.days_left("2026-12-06", today))
    check("支持 2026/12/6 这种写法", sp.days_left("2026/12/6", today) == 81)
    check("空日期返回 0", sp.days_left("", today) == 0)
    check("非法日期不炸", sp.days_left("明年再说", today) == 0)
    check("过去的日期是负数", sp.days_left("2026-09-01", today) < 0)

    print("[4] 阶段划分随天数变形")
    check("≤7 天只有「考前一周」", [s[0] for s in sp.stages(5)] == ["考前一周·只做三件事"],
          [s[0] for s in sp.stages(5)])
    s21 = [s[0] for s in sp.stages(20)]
    check("≤21 天是 强化 + 冲刺", s21 == ["强化期", "冲刺期"], s21)
    s45 = [s[0] for s in sp.stages(40)]
    check("≤45 天是 基础 + 强化 + 冲刺", s45 == ["基础期", "强化期", "冲刺期"], s45)
    s90 = [s[0] for s in sp.stages(90)]
    check(">45 天有 4 段（含考前一周）", len(s90) == 4 and s90[-1] == "考前一周", s90)
    check("阶段天数加起来大致等于总天数",
          abs(sum(x[1] for x in sp.stages(90)) - 90) <= 8,
          sum(x[1] for x in sp.stages(90)))

    print("[5] 每日课表随时长变化")
    for h, lo in ((2, 2), (4, 4), (6, 6), (8, 6)):
        tbl, tot = sp.daily_schedule(h, "电气/自动化")
        check(f"每天 {h} 小时 → 课表总量 {tot}h（≥{lo}h 且不超太多）", lo - 0.6 <= tot <= h + 1.5,
              (h, tot))
    tbl, _ = sp.daily_schedule(6, "电气/自动化", sprint=True)
    check("冲刺模式课表含「必背/背记」环节", any("背" in t for _, t, _ in tbl), tbl[:2])
    check("课表每行都是 (时段, 任务, 时长)", all(len(x) == 3 for x in tbl))

    print("[6] 生成完整方案（云南烟草冲刺场景）")
    p = sp.generate("烟草·云南中烟工业（生产系统）", role="电气/自动化",
                    exam_date="2026-12-06", hours=6, today=today)
    check("目标识别正确", p["short"] == "云南中烟", p["short"])
    check("剩余天数带进来", p["days_left"] == 81, p["days_left"])
    check("总小时数 = 天数 × 每天", p["total_hours"] == 81 * 6, p["total_hours"])
    check("专业知识方向 = 电气/自动化", p["role_key"] == "电气/自动化")
    md = sp.to_markdown(p)
    for want in ("一、考情分析", "二、重点排序", "三、分阶段计划", "每日时间表",
                 "四、必背清单", "五、真题与资料来源", "六、面试准备", "七、避坑"):
        check(f"方案含章节「{want}」", want in md, None)
    check("考情分析把权重写清楚了", "%" in md and "行政职业能力测验" in md)
    check("重点排序里有「可以放弃什么」", "战略性放弃" in md)
    check("倒推阶段写进了方案", "基础期" in md or "强化期" in md or "冲刺期" in md)
    check("必背清单里专业方向对上了电气", "电机与拖动" in md or "PLC" in md, None)
    check("资料来源里有国家局官网", "tobacco.gov.cn" in md)
    check("提醒了「先交钱的是骗子」", "骗子" in md)
    check("提醒了烟草 1 单位 1 岗", "同一批次只能报 1 个单位 1 个岗位" in md)

    print("[7] 云南烟草模板的行业常识必须真能用")
    mem = p["memorize"]
    common = " ".join(mem["烟草行业常识（必背）"])
    for kw in ("一套机构、两块牌子", "商业系统", "生产系统", "两烟", "专卖法",
               "1991", "准运证", "电子烟", "FCTC", "烟叶税"):
        check(f"行业常识含「{kw}」", kw in common, None)
    check("提到了云南烟叶占比", "1/3" in common)
    check("提到了大理是产区（本地生源用得上）", "大理" in common)
    prof = mem["专业知识（按岗位方向）"]
    for k in ("电气 / 自动化", "机械", "计算机 / 电子信息"):
        check(f"专业知识分三套，含「{k}」", any(k in x for x in prof), list(prof))

    print("[8] 短周期（只剩几天）也要出完整方案")
    p2 = sp.generate("烟草·云南省烟草专卖局（商业系统）", role="信息化",
                     exam_date=(today + timedelta(days=5)).isoformat(), hours=8, today=today)
    check("剩 5 天判为冲刺档", p2["days_left"] == 5)
    md2 = sp.to_markdown(p2)
    check("只有一段阶段（考前一周）", "考前一周" in md2)
    check("仍然含必背清单与资料来源", "必背清单" in md2 and "资料来源" in md2)

    print("[9] 自定义单位 / 日期没填也不崩")
    p3 = sp.generate("云南省交通投资建设集团", role="机电", exam_date="", hours=4, today=today)
    check("自定义单位走通用档案", p3["short"] == "央国企", p3["short"])
    check("保留了用户填的单位名", "云南省交通投资建设集团" in p3["target_raw"])
    md3 = sp.to_markdown(p3)
    check("日期没填也能出方案并给出提示", "请把日期改成未来" in md3, None)
    check("缺日期时阶段表仍能渲染", "| 阶段 |" in md3)

    print("[10] 默认考试日与导出")
    for t in sp.targets():
        sh = sp.profile_of(t)["short"]
        dd = sp.default_exam_date(sh, today)
        ok = bool(sp._parse_date(dd)) and (sp._parse_date(dd) - today).days > 0
        check(f"「{sh}」默认考试日是未来日期（{dd}）", ok, dd)
    check("默认日落在 10–12 月（秋招节奏）",
          sp.default_exam_date("云南中烟", today)[5:7] in ("10", "11", "12"),
          sp.default_exam_date("云南中烟", today))

    print(f"\n结果: {PASS} 通过, {FAIL} 失败")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
