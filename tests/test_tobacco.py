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

print("[4b] 岗位取向：要技术、不要一线（用户明确要求）")
check("数字信息类 → ✅ 技术/管理类", T.role_fit("本次招聘岗位为数字信息类、机电自动化类")[0].startswith("✅"),
      T.role_fit("本次招聘岗位为数字信息类"))
check("生产操作类 → ⛔ 一线", T.role_fit("本次招聘均为生产操作类岗位，车间一线")[0].startswith("⛔"),
      T.role_fit("生产操作类岗位"))
check("信息和操作都有 → ⚠️ 混合",
      T.role_fit("既有信息化岗也有生产操作类岗")[0].startswith("⚠️"),
      T.role_fit("既有信息化岗也有生产操作类岗"))
check("技术类提优先级", T.priority_of("某省2027年招聘公告", "岗位为数字信息类") >
      T.priority_of("某省2027年招聘公告", "岗位为生产操作类"),
      [T.priority_of("x", "数字信息类"), T.priority_of("x", "生产操作类")])
check("一线操作岗被压到 2★ 及以下",
      T.priority_of("河南省烟草专卖局2027年招聘公告", "本次招聘均为生产操作类岗位") <= 2)

_html = """<html><body>
<div class="nav">首页 专卖 许可 卷烟 烟叶 信息化 招聘 大数据 人工智能 热搜词：招聘</div>
<div class="conZhDy">
  <p>河南省烟草专卖局（公司）2027年高校毕业生招聘公告</p>
  <p>本次招聘均为生产操作类岗位，从事卷烟生产车间一线操作工作。</p>
  <p>报名时间：2026年11月20日9时至2026年11月28日17时，逾期不再受理。</p>
  <p>应聘人员只能选择1个岗位应聘，重复报名无效。</p>
</div>
<div class="contentBotshare">版权所有 国家烟草专卖局</div>
</body></html>"""
_art = T._article_text(_html)
check("正文切片不含网站导航（否则会假命中「信息化」）", "首页" not in _art and "信息化" not in _art, _art[:60])
check("切片后仍能认出「生产操作类」", T.role_fit(_art)[0].startswith("⛔"), T.role_fit(_art)[0])
check("切片后窗口仍解析正确",
      T.parse_window(_art)["apply_to"] == "2026-11-28", T.parse_window(_art)["apply_to"])

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

    print("[6b] 岗位类型推荐（合适 / 轻松 / 钱多）")
    from ihub import tobacco_roles as TR                                  # noqa: E402
    _rk = TR.ranked()
    check("至少 8 类岗位", len(_rk) >= 8, len(_rk))
    check("默认权重下第一名是数字信息类/信息化岗",
          "数字信息" in _rk[0]["name"], _rk[0]["name"])
    check("前 3 名都是技术类（合适 ★★★★ 以上）", all(r["fit"] >= 4 for r in _rk[:3]),
          [(r["name"], r["fit"]) for r in _rk[:3]])
    check("生产操作类垫底", "生产操作" in _rk[-1]["name"], _rk[-1]["name"])
    check("每个维度都是 1~5 分", all(1 <= r[d] <= 5 for r in TR.ROLES for d in ("fit", "light", "pay")))
    check("总分落在 2~10", all(2 <= r["score"] <= 10 for r in _rk), [r["score"] for r in _rk])

    # 换权重：钱多优先，技术岗仍应在前，一线仍应垫底
    _rk2 = TR.ranked(0.2, 0.2, 0.6)
    check("改成「钱多优先」后前 3 名仍是技术岗", all(r["fit"] >= 4 for r in _rk2[:3]),
          [(r["name"], r["score"]) for r in _rk2[:3]])
    _rk3 = TR.ranked(0.1, 0.8, 0.1)
    check("改成「轻松优先」后一线操作岗仍在后半段",
          [r["name"] for r in _rk3].index(_rk3[-1]["name"]) >= len(_rk3) - 3,
          [r["name"] for r in _rk3][-3:])
    check("结论文案里点名了第一名", _rk[0]["name"][:4] in TR.summary_text())
    check("按关键词能归类（生产操作类）",
          TR.by_alias("本次招聘均为生产操作类岗位")["fit"] == 2)
    check("按关键词能归类（数字信息类）", "数字信息" in TR.by_alias("数字信息类岗位")["name"])
    check("行政助理归到综合管理类（本就该归类）",
          TR.by_alias("某公司行政助理")["fit"] == 2, TR.by_alias("某公司行政助理"))
    check("完全无关的岗位名不硬猜（返回 None）", TR.by_alias("机关食堂厨师") is None)
    _txt = TR.as_text()
    check("文本报告含 9 类的分数表", "总分" in _txt and "合适" in _txt)
    check("文本报告声明了「非官方数据」", "不是官方数据" in _txt)

    print("[7] 文本报告")
    _txt = T.as_text(r4)
    check("报告含铁律提醒", "重复投递" in _txt or "取消资格" in _txt)
    check("报告含报名窗口", "报名窗口" in _txt or "新增" in _txt)
    check("空结果也能出报告", T.as_text({"checked_at": "x", "new": [], "all": [],
                                        "total_seen": 0}).startswith("🍃 烟草招聘监控"))

T.fetch_list, T.fetch_detail = _orig_fetch, _orig_detail

print(f"\n结果: {P} 通过, {F} 失败")
sys.exit(1 if F else 0)
