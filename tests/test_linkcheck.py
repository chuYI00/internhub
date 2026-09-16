# -*- coding: utf-8 -*-
"""链接体检的**离线规则**自测（第 2 步重构的静态防线）。

这些用例不需要联网：判的是「规则本身对不对」——
伪直达能不能认出来、能不能拦在企业官方按钮之外、域名匹配符不符合最长键逻辑。
联网体检结果（data/link_health.json）另有一条用例做结构校验。

运行： venv\\Scripts\\python.exe tests\\test_linkcheck.py
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
    from ihub import linkcheck as lc

    print("[1] 伪直达识别（点开只能看到搜索引擎结果页）")
    fakes = [
        "https://www.baidu.com/s?wd=site%3Aiguopin.com%20昆明",
        "https://www.baidu.com/s?wd=2027届 秋招 国企 汇总表",
        "https://weixin.sogou.com/weixin?type=2&query=国资小新",
        "http://www.baidu.com/s?wd=云南中烟",
        "https://www.sogou.com/web?query=招聘",
        "https://www.bing.com/search?q=云南+国企",
    ]
    for u in fakes:
        check(f"判为伪直达：{u[:46]}…", lc.is_fake_direct(u))

    print("[2] 真链接不能被误判成伪直达")
    reals = [
        "https://www.iguopin.com/",
        "https://yn.tobacco.gov.cn/",
        "https://hr.ynairport.com/zp/",
        "https://zhaopin.csg.cn",
        "https://cauc.bysjy.com.cn/module/careers?menu_id=28135",
        "http://job.mohrss.gov.cn",
        "https://job.ncss.cn/student/jobs/index.html?keyword=云南",
    ]
    for u in reals:
        check(f"不误判：{u[:50]}", not lc.is_fake_direct(u))

    print("[3] 平台站识别（信息是真的，但不是企业官方页）")
    for u in ("https://www.zhipin.com/", "https://xiaoyuan.zhaopin.com/",
              "https://www.iguopin.com/", "https://www.shixiseng.com/"):
        check(f"判为平台站：{u}", lc.is_platform(u))
    check("平台站不能被当官方投递按钮",
          not lc.can_be_official_button("https://www.zhipin.com/"))
    check("伪直达不能被当官方投递按钮",
          not lc.can_be_official_button("https://www.baidu.com/s?wd=x"))
    check("企业官网可以当官方投递按钮",
          lc.can_be_official_button("https://www.ynzy-tobacco.com/"))
    check("企业专属 ATS 子域算官方（北森/Moka）",
          lc.is_ats("https://ynjstzkg.zhiye.com/") and
          lc.can_be_official_button("https://ynjstzkg.zhiye.com/"))

    print("[4] 域名解析与「跳站」判定")
    check("domain_of 去掉 www.", lc.domain_of("https://www.tobacco.gov.cn/x") == "tobacco.gov.cn",
          lc.domain_of("https://www.tobacco.gov.cn/x"))
    check("registrable 认 .com.cn", lc.registrable("zhaopin.csg.cn") == "csg.cn",
          lc.registrable("zhaopin.csg.cn"))
    check("registrable 认 .gov.cn", lc.registrable("hrss.yn.gov.cn") == "yn.gov.cn",
          lc.registrable("hrss.yn.gov.cn"))
    check("子域算同站", lc.registrable(lc.domain_of("https://hr.ynairport.com/zp/"))
          == lc.registrable(lc.domain_of("https://intranet.ynairport.com/zhaopin/index.jhtml")))

    print("[5] 静态判定：能判死的当场判死")
    for u in fakes[:3]:
        g, why = lc.static_verdict("某单位", u)
        check(f"静态判 C：{u[:38]}…", g == "C", (g, why))
    check("空链接判 C", lc.static_verdict("x", "")[0] == "C")
    check("缺协议的判 C", lc.static_verdict("x", "www.baidu.com")[0] == "C")
    check("平台站静态先标 P?", lc.static_verdict("BOSS", "https://www.zhipin.com/")[0] == "P?")
    check("正常官网留给联网体检", lc.static_verdict("中烟", "https://www.ynzy-tobacco.com/")[0] == "?")

    print("[6] 联网结果 → 等级（喂假数据，不真联网）")
    # 反爬不能当死链 —— 本机浏览器是好的
    g, why = lc.net_verdict("云南电网", "https://zhaopin.csg.cn",
                            {"status": 412, "final_url": "https://zhaopin.csg.cn",
                             "title": "", "body_len": 0, "snippet": ""})
    check("412 反爬 → D 待本机复查（不是 C 死链）", g == "D", (g, why))
    # 报错也不能当死链
    g, why = lc.net_verdict("银行", "https://job.icbc.com.cn/", {"error": "SSLError: xxx"})
    check("沙箱连不上 → D（不是 C）", g == "D", (g, why))
    # 真 404 才是 C
    g, why = lc.net_verdict("某站", "https://x.com/", {"status": 404, "final_url": "https://x.com/",
                                                      "title": "404", "body_len": 50, "snippet": ""})
    check("404 → C 淘汰", g == "C", (g, why))
    # 跳到平台站 → P（不能当官方页）
    g, why = lc.net_verdict("某公司", "https://hr.example.com/",
                            {"status": 200, "final_url": "https://www.zhipin.com/",
                             "title": "BOSS直聘", "body_len": 9000, "snippet": "BOSS"},
                            words=("某公司",))
    check("跳到招聘平台 → P", g == "P", (g, why))
    # 正常 A
    g, why = lc.net_verdict("云南中烟", "https://www.ynzy-tobacco.com/",
                            {"status": 200, "final_url": "https://www.ynzy-tobacco.com/",
                             "title": "云南中烟工业有限责任公司", "body_len": 5000,
                             "snippet": "云南中烟 招聘 公告"}, words= ("中烟", "烟草"))
    check("企业官网 + 关键词命中 → A", g == "A", (g, why))
    # 空壳 ATS → D
    g, why = lc.net_verdict("云南建投", "https://ynjstzkg.zhiye.com/",
                            {"status": 200, "final_url": "https://ynjstzkg.zhiye.com/",
                             "title": "云南建投", "body_len": 80,
                             "snippet": "<div id=\"app\"></div> 正在加载"})
    check("企业 ATS 空壳 → D 待本机确认（不降成 B）", g == "D", (g, why))

    print("[7] 项目现状：官方投递字段里不能再有伪直达")
    from ihub import channels, yunnan, platforms, campus_channels as cc
    bad = [(c, u) for c, u in channels.OFFICIAL_URLS.items() if lc.is_any_search(u)]
    check("channels.OFFICIAL_URLS 无伪直达/平台页", not bad, bad[:3])
    bad2 = [(u["name"], u.get(k)) for u in yunnan.all_units()
            for k in ("portal", "apply") if lc.is_any_search(u.get(k) or "")]
    check("yunnan 官方字段无伪直达/平台页", not bad2, bad2[:3])
    bad3 = [(u["name"], u["url"]) for u in
            [{"name": x["name"].split("（")[0], "url": x["url"]} for x in platforms.all_platforms()]
            if lc.is_fake_direct(u["url"])]
    check("platforms 平台矩阵无伪直达", not bad3, bad3[:3])
    bad4 = cc.fake_direct_left()
    check("campus_channels 渠道清单无伪直达", not bad4, bad4[:3])
    check("campus_channels 的官方入口里没有搜索引擎链接",
          all(not lc.is_fake_direct(u) for _, u, _ in cc.official_entries()))
    check("静默搜索说明给了关键词（不给假链接）",
          all(("关键词" in how) for _, _, how in cc.manual_search_notes()))

    print("[8] channels 的「最长键匹配」不能退化")
    check("云南中烟 → 中烟官网", channels.official_for("云南中烟工业有限责任公司")
          == "https://www.ynzy-tobacco.com/")
    check("云南机场 → 航产投招聘页", channels.official_for("云南航空产业投资集团（云南机场集团）")
          == "https://hr.ynairport.com/zp/")
    check("南方电网云南 → 电网招聘系统", channels.official_for("中国南方电网云南电网")
          == "https://zhaopin.csg.cn")
    check("云南红塔银行不被「红塔集团」抢走",
          channels.official_for("云南红塔银行") != "https://www.ynzy-tobacco.com/",
          channels.official_for("云南红塔银行"))
    check("不认识的返回空", channels.official_for("某某科技") == "")
    info = channels.official_info("云南中烟工业有限责任公司")
    check("official_info 返回 url/grade/label/ok", all(
        k in info for k in ("url", "grade", "label", "reason", "ok")), info)
    check("official_info 未收录时 ok=False", channels.official_info("某某科技")["ok"] is False)

    print("[9] 体检存档（如果有）结构正确")
    saved = lc.load_saved()
    if saved:
        check("每条都有 label/url/grade/reason",
              all(all(k in r for k in ("label", "url", "grade", "reason")) for r in saved))
        check(f"等级只出现 A/P/B/C/D（{len(saved)} 条）",
              all(r["grade"] in ("A", "P", "B", "C", "D") for r in saved),
              sorted({r["grade"] for r in saved}))
        s = lc.summary(saved)
        check("summary 计数与条数一致", s["total"] == len(saved), s)
        md = lc.report_md(saved, "2026-09-16 22:00")
        check("报告含分级标题", "A 级" in md and "D 级" in md)
    else:
        print("  [--] 还没跑过 run_linkcheck.py，跳过（不影响其它用例）")

    print(f"\n结果: {PASS} 通过, {FAIL} 失败")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
