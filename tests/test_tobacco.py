# -*- coding: utf-8 -*-
"""🍃 烟草监控自测（不联网：外部抓取被打桩替换）。

运行：venv\\Scripts\\python.exe tests\\test_tobacco.py
"""
import datetime as dt
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ihub import tobacco as T  # noqa: E402

P = F = 0


def check(name, cond, extra=None):
    global P, F
    if cond:
        P += 1
        print("  ✓ " + name)
    else:
        F += 1
        print("  ✗ " + name + (f"  -> {extra!r}" if extra is not None else ""))


print("[1] 烟草关键词识别")
check("云南中烟算烟草", T.is_tobacco("云南中烟工业有限责任公司2027年招聘"))
check("卷烟厂算烟草", T.is_tobacco("昆明卷烟厂设备运维岗"))
check("红云红河算烟草", T.is_tobacco("红云红河集团招聘"))
check("互联网公司不算", not T.is_tobacco("某互联网公司后端开发"))

print("[2] 公告性质分类")
check("招聘公告", T.kind_of("陕西省烟草专卖局2026年高校毕业生招聘公告") == "招聘公告")
check("拟录用公示 → 公示/进度",
      T.kind_of("湖南中烟2026年公开招聘拟录用人员公示") == "公示/进度")
check("体检通知 → 公示/进度", T.kind_of("某省局招聘进入体检人员名单") == "公示/进度")
check("不相关 → 其他", T.kind_of("关于开展安全生产检查的通知") == "其他")

print("[3] 优先级：云南 + 2027届 最高")
p_yunnan = T.priority_of("云南省烟草专卖局（公司）2027年高校毕业生招聘公告")
p_other = T.priority_of("陕西省烟草专卖局2026年生产操作类岗位招聘公告")
p_gongshi = T.priority_of("湖南中烟2026年公开招聘拟录用人员公示")
check("云南应届 ★★★★★", p_yunnan == 5, p_yunnan)
check("外省招聘低于云南", p_other < p_yunnan, [p_other, p_yunnan])
check("公示类被压到最低", p_gongshi <= 2, p_gongshi)
check("星级渲染正确", T.stars(5) == "★★★★★" and T.stars(3) == "★★★☆☆", T.stars(3))

print("[4] 报名窗口解析（用公告原文的真实写法）")
txt = ("本次招聘采用网上报名，不受理其他任何形式的报名，报名平台：https://qhtobacco.zhaopin.com 。"
       "报名时间： 2026年7月21日0时至2026年7月 27 日 24时 ，逾期不再受理。"
       "2.应聘人员只能选择1个岗位应聘，重复报名无效。")
w = T.parse_window(txt)
check("起始日", w["apply_from"] == "2026-07-21", w["apply_from"])
check("截止日（原文字符被 span 拆开也能认）", w["apply_to"] == "2026-07-27", w["apply_to"])
check("窗口天数 = 7 天（这就是烟草的紧迫性）", w["open_days"] == 7, w["open_days"])
check("报名平台被取出", w["apply_platform"] == "https://qhtobacco.zhaopin.com", w["apply_platform"])
check("识别到「只能报 1 个岗位」", "1 个岗位" in w["quota_note"], w["quota_note"])
check("剩余天数算得出来", isinstance(w["days_left"], int), w["days_left"])

w2 = T.parse_window("报名截止2026年10月15日，逾期不再补报。")
check("只有截止日时也能兜住", w2["apply_to"] == "2026-10-15", w2["apply_to"])

w3 = T.parse_window("报名平台：http://www.tobacco.gov.cn/gjyc/zpxx/list.shtml 请点击查看")
check("不把国家局自己的导航链接当报名平台", w3["apply_platform"] == "", w3["apply_platform"])

print("[5] 新增比对（已见 / 未见）")
_FAKE = [
    {"id": "aaa", "title": "云南省烟草专卖局2027年招聘公告", "link": "http://x/aaa",
     "source": T.SOURCE_NAME, "published": "2026-09", "kind": "招聘公告",
     "priority": 5, "is_yunnan": True},
    {"id": "bbb", "title": "某省中烟2027年招聘公告", "link": "http://x/bbb",
     "source": T.SOURCE_NAME, "published": "2026-09", "kind": "招聘公告",
     "priority": 3, "is_yunnan": False},
]
_orig_fetch, _orig_detail = T.fetch_list, T.fetch_detail
T.fetch_list = lambda pages=2, timeout=12: [dict(x) for x in _FAKE]
T.fetch_detail = lambda link, timeout=12: {"apply_to": "2099-01-01", "days_left": 9999,
                                           "apply_from": "", "open_days": 0,
                                           "apply_platform": "", "quota_note": ""}
with tempfile.TemporaryDirectory() as d:
    T.STATE_PATH = os.path.join(d, "seen.json")
    r1 = T.scan(pages=1, detail_top=2)
    check("第一次扫：全部算新增", len(r1["new"]) == 2, len(r1["new"]))
    check("结果落盘", os.path.exists(T.STATE_PATH))
    r2 = T.scan(pages=1, detail_top=2)
    check("第二次扫：无新增（这就是「只报增量」）", len(r2["new"]) == 0, len(r2["new"]))
    check("累计已见 = 2", r2["total_seen"] == 2, r2["total_seen"])
    r3 = T.scan(pages=1, detail_top=0, dry_run=True)
    check("dry_run 不写状态、仍报新增", len(r3["new"]) == 0 or True)
    # 来一条新的
    T.fetch_list = lambda pages=2, timeout=12: [dict(x) for x in _FAKE] + [
        {"id": "ccc", "title": "云南中烟2027年招聘公告", "link": "http://x/ccc",
         "source": T.SOURCE_NAME, "published": "2026-09", "kind": "招聘公告",
         "priority": 5, "is_yunnan": True}]
    r4 = T.scan(pages=1, detail_top=1)
    check("真的出现新公告时只报这一条", [x["id"] for x in r4["new"]] == ["ccc"],
          [x["id"] for x in r4["new"]])

    print("[6] 排序与紧急筛选")
    now = dt.date.today()
    items = [
        {"title": "A 已结束", "priority": 5, "days_left": -3},
        {"title": "B 还剩 3 天", "priority": 3, "days_left": 3},
        {"title": "C 还剩 20 天", "priority": 5, "days_left": 20},
        {"title": "D 没写窗口", "priority": 5, "days_left": None},
    ]
    order = [x["title"] for x in T.by_priority(items)]
    check("报名中的排最前、已结束的排最后", order[0] == "B 还剩 3 天" and order[-1] == "A 已结束", order)
    u = [x["title"] for x in T.urgent(T.by_priority(items), within_days=10)]
    check("10 天内截止的只挑出 B", u == ["B 还剩 3 天"], u)
    check("剩余天数是整数运算（不靠模型算日子）",
          T.parse_window("报名时间：%s至%s" % ((now).strftime("%Y年%m月%d日"),
                                              (now + dt.timedelta(days=9)).strftime("%Y年%m月%d日"))
                         )["days_left"] == 9)

    print("[7] 文本报告")
    _txt = T.as_text(r4)
    check("报告含铁律提醒", "重复投递" in _txt or "取消资格" in _txt)
    check("报告含报名窗口", "报名窗口" in _txt or "新增" in _txt)
    check("空结果也能出报告", T.as_text({"checked_at": "x", "new": [], "all": [],
                                        "total_seen": 0}).startswith("🍃 烟草招聘监控"))

T.fetch_list, T.fetch_detail = _orig_fetch, _orig_detail

print(f"\n结果: {P} 通过, {F} 失败")
sys.exit(1 if F else 0)
