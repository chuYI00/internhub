# -*- coding: utf-8 -*-
"""采集链路自测：跳转壳解码 / 公司名提取 / 数据源并集 / 官网入口匹配。

运行：venv\\Scripts\\python.exe tests\\test_weblist.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ihub import channels                                   # noqa: E402
from ihub.crawlers.weblist import (_company_from_title,     # noqa: E402
                                   _real_apply_url, load_sources)

P = F = 0


def check(name, cond, extra=None):
    global P, F
    if cond:
        P += 1
        print("  ✓ " + name)
    else:
        F += 1
        print("  ✗ " + name + (f"  -> {extra!r}" if extra is not None else ""))


print("[1] 跳转壳 → 企业官方投递地址（应届生求职网的 thirdlink）")
check("解出建行校招网申页",
      _real_apply_url("https://q.yingjiesheng.com/thirdlink?url="
                      "https%3A%2F%2Fjob2.ccb.com%2Fcn%2Fjob%2Fplan_index.html%3FplanType%3DXY")
      == "https://job2.ccb.com/cn/job/plan_index.html?planType=XY",
      _real_apply_url("https://q.yingjiesheng.com/thirdlink?url=https%3A%2F%2Fjob2.ccb.com%2F"))
check("解出北森 hotjob 入口",
      _real_apply_url("https://q.yingjiesheng.com/thirdlink?url=https%3A%2F%2Fwecruit.hotjob.cn%2FSU620%2Fmc%2F")
      .startswith("https://wecruit.hotjob.cn/"))
check("解出飞书招聘入口",
      _real_apply_url("https://q.yingjiesheng.com/thirdlink?url=https%3A%2F%2Fx.jobs.feishu.cn%2F123")
      .startswith("https://x.jobs.feishu.cn/"))
check("不是壳的链接保持原样", _real_apply_url("https://campus.51job.com/cimc/") == "")
check("空值不炸", _real_apply_url("") == "" and _real_apply_url(None) == "")

print("[2] 公告标题 → 公司名")
cases = [("中国建设银行2027年度校园招聘", "中国建设银行"),
         ("第一创业证券2027届校园招聘", "第一创业证券"),
         ("中集集团2027届校招", "中集集团"),
         ("汇丰银行管培生计划", "汇丰银行")]
for title, want in cases:
    got = _company_from_title(title)
    check(f"{title} → {want}", got == want, got)
check("乱七八糟的标题不硬编出公司名", _company_from_title("招聘") == "",
      _company_from_title("招聘"))

print("[3] 数据源清单取并集（历史上的双份遮蔽 bug）")
srcs = load_sources()
check("源数量 ≥27", len(srcs) >= 27, len(srcs))
names = {s["name"] for s in srcs}
for kw in ("应届生求职网·2027校招公告", "云南省教育厅·公示公告", "昆明市人社局·通知公告",
           "云南航空产业投资集团·招聘"):
    check(f"包含 {kw}", kw in names)
check("应届生源开了 auto_company", any(s.get("auto_company") for s in srcs))
check("每个源都有 name", all(s.get("name") for s in srcs))

print("[4] 官网入口匹配（必须取最长键，别把「红塔银行」配成「红塔集团」）")
check("云南中烟 → 中烟官网", channels.official_for("云南中烟工业有限责任公司") == "https://www.ynzy-tobacco.com/")
check("云南机场 → 航产投招聘页", channels.official_for("云南航空产业投资集团（云南机场集团）") == "https://hr.ynairport.com/zp/")
check("南方电网云南 → 电网招聘系统", channels.official_for("中国南方电网云南电网") == "https://zhaopin.csg.cn")
check("不认识的空公司名返回空", channels.official_for("某某科技") == "")
check("空公司名不炸", channels.official_for("") == "")

print(f"\n结果: {P} 通过, {F} 失败")
sys.exit(1 if F else 0)
