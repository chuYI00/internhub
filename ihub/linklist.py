# -*- coding: utf-8 -*-
"""投递入口清单：把「每条岗位去哪儿投」导成纯文本 / CSV。

为什么要单独做成模块：这段逻辑原本长在 app.py 里，只能靠 Streamlit 渲染才能验证；
抽出来后既能被单元测试覆盖，也能在命令行直接生成成品（不用开网页）。

核心原则：**不把"来源平台的页面"伪装成"企业官网投递页"**。
很多来源（高校就业网、实习僧、公众号）抓到的链接就是它自家的详情页，
那不算官方入口 —— 清单里会明说"该来源未提供官方入口"，避免你白点一趟。
"""

HEADER = [
    "投递入口清单（先进官方页面 → 再用网申助手填表 → 再上传对应简历）",
    "=" * 62,
    "",
    "用法：① 点下面的官方入口进企业网申系统  ② 页面上点右下角「📝 网申助手」自动填",
    "      ③ 回本工具「🎯 投递工作台」生成这份岗位的定向简历并上传  ④ 标记已投防重复",
    "",
]


def _official_of(rec: dict) -> str:
    """取真正的官方投递入口；若它只是原链接的副本，视为"没有官方入口"。"""
    off = str(rec.get("企业官网") or rec.get("official_url") or "").strip()
    link = str(rec.get("link") or "").strip()
    if off and off == link:
        return ""
    return off


def apply_links_text(records) -> str:
    """records：可迭代的 dict，键用中文列名（企业官网/截止时间…）或英文列名都可以。"""
    L = list(HEADER)
    miss = 0
    for i, r in enumerate(records, 1):
        off = _official_of(r)
        if not off:
            miss += 1
        deadline = str(r.get("截止时间") or r.get("deadline") or "")[:10] or "见公告"
        L.append(f'[{i}] {r.get("title")}')
        L.append(f'    公司：{r.get("company")}　城市：{r.get("city")}　截止：{deadline}')
        L.append(f'    官方投递：{off if off else "—（该来源未提供官方入口，请按下面的原链接进）"}')
        L.append(f'    原链接：{r.get("link")}')
        L.append(f'    来源：{r.get("source")}')
        L.append("")
    if miss:
        L.append(f"注：{miss} 条没有官方入口 —— 高校就业网/公众号这类来源经常只给内推邮箱或"
                 f"跳转页，属正常；按原链接进去后一样能用网申助手填表。")
    else:
        L.append("注：本次全部岗位都拿到了官方投递入口。")
    return "\n".join(L)
