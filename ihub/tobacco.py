# -*- coding: utf-8 -*-
"""🍃 烟草招聘监控（专盯「别错过报名窗口」）。

为什么单独做一个模块
--------------------
烟草是所有央国企里**报名窗口最短、且最不能重复投**的一类：
- 网申窗口常常只有 7~10 天（实测公告原文：「报名时间：2026年7月21日0时至2026年7月27日24时，逾期不再受理」）；
- 同一批次只能报 1 个单位 1 个岗位，重复投递直接取消资格；
- 公告只发在固定几个官方口，错过就等下一批（可能半年）。

监控源头（实测可用）
--------------------
1. **国家烟草专卖局 · 人才招聘专栏**（唯一总发布口，各省公告都在这里首发）
   http://www.tobacco.gov.cn/gjyc/zpxx/list.shtml   ← 服务端渲染，能抓；翻页=list_2.shtml
   详情页能提到 **报名时间 / 报名平台网址 / 招聘对象 / 是否限制报考岗位数**。
2. 本地已有数据源里标题含烟草关键词的条目（高校就业网、人社厅、应届生等）。

云南中烟、云南省局官网是 Vue 前端渲染，抓不到 —— 但它们发的公告同样会出现在国家局专栏，
所以盯住国家局就够了。

状态文件：data/tobacco_seen.json（记录已见过的公告，用来算"新增"）。
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import re
from urllib.parse import urljoin

import requests

from . import config

# ────────────────────── 常量 ──────────────────────

LIST_BASE = "http://www.tobacco.gov.cn/gjyc/zpxx/"
LIST_URLS = [LIST_BASE + "list.shtml"] + [f"{LIST_BASE}list_{n}.shtml" for n in range(2, 6)]
SOURCE_NAME = "国家烟草专卖局·人才招聘专栏"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# 标题里出现这些词 = 和烟草系统有关
TOBACCO_KW = ["烟草", "中烟", "卷烟", "烟叶", "专卖局", "红塔", "红云红河", "烟机",
              "烟草公司", "复烤", "卷烟厂"]
# 你重点要盯的地域/批次（明确过：昆明 + 大理都投）
YUANNAN_KW = ["云南", "云烟", "红塔", "红云红河", "昆明", "大理", "曲靖", "玉溪", "红河", "楚雄"]

# ── 岗位取向：你明确要「偏技术、不要一线」────────────────────────────
# 命中这些 = 对口（技术和专业管理岗）
ROLE_TECH_KW = ["数字信息", "信息化", "信息技术", "信息中心", "计算机", "软件", "网络", "网络安全",
                "大数据", "人工智能", "数据", "系统", "自动化", "电气", "机电", "设备", "仪表",
                "智能制造", "智能", "运维", "研发", "技术", "工程师", "专业技术", "管理类", "网信"]
# 命中这些 = 一线/操作岗（你说了不投，自动降级，别在名单里浪费注意力）
ROLE_FRONT_KW = ["生产操作", "操作类", "操作岗", "车间", "一线", "烟叶收购", "收购", "分拣", "包装",
                 "司炉", "辅助", "安保", "消防", "稽查", "访销", "客户经理", "送货", "烟站",
                 "仓库", "养护", "厨师", "司机", "卷烟机操作"]

STATE_PATH = os.path.join(config.DATA_DIR, "tobacco_seen.json")

_ITEM_RE = re.compile(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.S | re.I)
_TAG_RE = re.compile(r"<[^>]+>")
_DATE_URL_RE = re.compile(r"/zpxx/(\d{4})(\d{2})/")
_WINDOW_RE = re.compile(
    r"报名(?:时间|期限)[:：]?(20\d{2})年(\d{1,2})月(\d{1,2})日?(\d{1,2})?时?"
    r"(?:至|到|-|—|~|～)?(20\d{2})年(\d{1,2})月(\d{1,2})日?(\d{1,2})?时?")
_WINDOW_ONE_RE = re.compile(
    r"(?:报名|投递)?(?:截止|截至)[^\d]{0,6}(20\d{2})年(\d{1,2})月(\d{1,2})日")
_PLATFORM_RE = re.compile(
    r"https?://[A-Za-z0-9.\-]+(?:zhaopin|hotjob|zhiye|51job|liepin|moka|feishu|myworkday|"
    r"tal\.cn|tobacco|chinahr|ciic|zhaopin\.com)[A-Za-z0-9./_\-?=&%]*", re.I)
_QUOTA_RE = re.compile(r"只能(?:选择|报考|应聘)\s*1\s*个|重复(?:报名|投递|应聘)|只能报(?:考)?一个")

# 公告正文容器（实测：国家局详情页正文在 div.conZhDy 里，到 div.contentBotshare 结束）
_BODY_START_RE = re.compile(r'<(?:div|section)[^>]+(?:id|class)="[^"]*conZhDy[^"]*"', re.I)
_BODY_END_RE = re.compile(r'<(?:div|section)[^>]+(?:id|class)="[^"]*(?:contentBotshare|conXxlyShare)[^"]*"', re.I)


def _article_text(html: str) -> str:
    """只取**公告正文**，不要整页文字。

    整页文字里带着网站导航（导航里就有「信息化」「招聘」这些词），
    用它判断岗位取向会假命中 —— 比如一份"生产操作类"公告也会被判成技术类。
    """
    m = _BODY_START_RE.search(html or "")
    if not m:
        return _clean(html)
    gt = html.find(">", m.start())                    # 跳过开标签本身
    start = (gt + 1) if gt != -1 else m.start()
    endm = _BODY_END_RE.search(html, start)
    seg = html[start: endm.start() if endm else len(html)]
    return _clean(seg)


def _clean(t: str) -> str:
    return re.sub(r"\s+", " ", _TAG_RE.sub("", t or "")).strip()


def _squeeze(s: str) -> str:
    """公告正文里数字常被 span 拆开（"2026年7月 27 日"），比对前先去掉空白。"""
    return re.sub(r"\s+", "", s or "")


def is_tobacco(text: str) -> bool:
    t = text or ""
    return any(k in t for k in TOBACCO_KW)


def kind_of(title: str) -> str:
    """公告性质：招聘公告（可行动） / 公示（拟录用，噪音） / 其他。"""
    t = title or ""
    if re.search(r"(公示|拟录用|拟聘|拟补录|体检|成绩|面试|资格初审)", t):
        return "公示/进度"
    if re.search(r"(招聘|招录|选调|引进|招收|考试聘用|报名)", t):
        return "招聘公告"
    return "其他"


def role_fit(text: str) -> tuple[str, str]:
    """判断岗位取向 —— 你明确过：**要偏技术，不要一线操作岗**。

    返回 (类型, 一句话说明)，用于自动给你排优先级、并在页面上直接标出来。
    """
    t = text or ""
    tech = [k for k in ROLE_TECH_KW if k in t]
    front = [k for k in ROLE_FRONT_KW if k in t]
    if front and not tech:
        return "⛔ 一线/操作类", f'含「{front[0]}」—— 你说了不要一线，已降级'
    if tech and front:
        return "⚠️ 混合（要核对岗位表）", f'既有「{tech[0]}」也有「{front[0]}」，进公告看具体岗位'
    if tech:
        return "✅ 技术/管理类", f'含「{tech[0]}」—— 与电子信息与自动化最对口'
    return "· 未标明", "标题没写岗位类型，进公告看一眼"


def priority_of(title: str, text: str = "") -> int:
    """优先级 1~5：云南/大理 + 2027届/应届 + **技术类** 最高；一线操作岗大幅降级。"""
    t = title or ""
    p = 2
    if any(k in t for k in YUANNAN_KW):
        p += 2
    if re.search(r"(2027|2026)", t):
        p += 1
    if "应届" in t or "高校毕业" in t:
        p += 1
    if kind_of(t) != "招聘公告":
        p -= 2
    role, _ = role_fit(f"{title} {text}")
    if role.startswith("✅"):
        p += 1
    elif role.startswith("⛔"):
        p -= 2
    return max(1, min(5, p))


def stars(p: int) -> str:
    return "★" * p + "☆" * (5 - p)


# ────────────────────── 抓列表 ──────────────────────

def fetch_list(pages: int = 2, timeout: int = 12) -> list[dict]:
    """抓国家烟草专卖局招聘专栏的公告列表（服务端渲染，可直接解析）。"""
    out, seen = [], set()
    for url in LIST_URLS[:max(1, pages)]:
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=timeout)
            r.encoding = r.apparent_encoding or "utf-8"
            html = r.text or ""
        except Exception:
            continue
        for m in _ITEM_RE.finditer(html):
            href, inner = m.group(1), m.group(2)
            if "/gjyc/zpxx/" not in href:
                continue
            title = _clean(inner)
            if len(title) < 8 or len(re.findall(r"[\u4e00-\u9fa5]", title)) < 4:
                continue
            full = urljoin(url, href)
            if full in seen:
                continue
            seen.add(full)
            dm = _DATE_URL_RE.search(full)
            published = f"{dm.group(1)}-{dm.group(2)}" if dm else ""
            role, role_note = role_fit(title)
            out.append({
                "id": hashlib.md5(full.encode("utf-8")).hexdigest()[:16],
                "title": title,
                "link": full,
                "source": SOURCE_NAME,
                "published": published,
                "kind": kind_of(title),
                "priority": priority_of(title),
                "role": role,
                "role_note": role_note,
                "is_yunnan": any(k in title for k in YUANNAN_KW),
            })
    return out


# ────────────────────── 抓详情：报名窗口 ──────────────────────

def parse_window(text: str) -> dict:
    """从公告正文里抠出报名窗口 / 报名平台 / 是否限制报考岗位数。

    公告原文形如：
      「报名时间：2026年7月21日0时至2026年7月27日24时，逾期不再受理。」
      「应聘人员只能选择1个岗位应聘，重复报名无效。」
    """
    s = _squeeze(text)
    res = {"apply_from": "", "apply_to": "", "apply_platform": "", "quota_note": "",
           "open_days": 0, "days_left": None}
    m = _WINDOW_RE.search(s)
    if m:
        y1, mo1, d1 = int(m.group(1)), int(m.group(2)), int(m.group(3))
        y2, mo2, d2 = int(m.group(5)), int(m.group(6)), int(m.group(7))
        try:
            res["apply_from"] = _dt.date(y1, mo1, d1).isoformat()
            res["apply_to"] = _dt.date(y2, mo2, d2).isoformat()
        except ValueError:
            pass
    if not res["apply_to"]:
        m2 = _WINDOW_ONE_RE.search(s)
        if m2:
            try:
                res["apply_to"] = _dt.date(int(m2.group(1)), int(m2.group(2)),
                                           int(m2.group(3))).isoformat()
            except ValueError:
                pass
    if res["apply_from"] and res["apply_to"]:
        try:
            a = _dt.date.fromisoformat(res["apply_from"])
            b = _dt.date.fromisoformat(res["apply_to"])
            res["open_days"] = (b - a).days + 1
        except ValueError:
            pass
    if res["apply_to"]:
        res["days_left"] = (_dt.date.fromisoformat(res["apply_to"]) - _dt.date.today()).days
    # 报名平台：正文里的报名系统地址。注意排除国家局自己的导航链接
    # （每页页脚都挂着 tobacco.gov.cn，不排掉会把"报名平台"识别成公告列表页）
    cands = [u.rstrip("。，、；") for u in _PLATFORM_RE.findall(s)]
    cands = [u for u in cands if "tobacco.gov.cn" not in u]
    if cands:
        res["apply_platform"] = cands[0]
    if _QUOTA_RE.search(s):
        res["quota_note"] = "⚠️ 公告明确：只能报 1 个岗位 / 重复报名无效"
    return res


def fetch_detail(link: str, timeout: int = 12) -> dict:
    """抓公告详情：报名窗口 + 报名平台 + 正文开头（用于判断岗位类型）。"""
    try:
        r = requests.get(link, headers={"User-Agent": UA}, timeout=timeout)
        r.encoding = r.apparent_encoding or "utf-8"
        html = r.text or ""
    except Exception:
        return {}
    body = _article_text(html)          # 只取正文，别把导航算进去
    res = parse_window(body)
    # 正文开头留着：公告里常写「本次招聘岗位：数字信息类、机电自动化类…」
    # 或明确写「生产操作类岗位」—— 用来判断是不是你要的技术岗。
    res["text_head"] = body[:1500]
    return res


# ────────────────────── 状态（已见集合） ──────────────────────

def load_seen() -> dict:
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            d = json.load(f)
            return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save_seen(seen: dict) -> None:
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(seen, f, ensure_ascii=False, indent=1)
    os.replace(tmp, STATE_PATH)


# ────────────────────── 主流程 ──────────────────────

def scan(pages: int = 2, detail_top: int = 8, only_recruit: bool = False,
         tech_only: bool = False, dry_run: bool = False) -> dict:
    """扫一遍并和"已见"比对。

    detail_top：对前 N 条**新**公告抓详情页，提取报名窗口（要发 N 次请求，别设太大）。
    tech_only：只看技术/管理类（滤掉一线操作岗）—— 你明确过不投一线，默认在页面上是勾选的。
    返回 {"checked_at", "new": [...], "all": [...], "total_seen"}，新条目带 `is_new=True`。
    """
    items = fetch_list(pages=pages)
    seen = load_seen()
    new = [it for it in items if it["id"] not in seen]

    # 只对新公告抓详情（省请求）；按优先级高的先抓
    new.sort(key=lambda x: -x["priority"])
    for i, it in enumerate(new):
        if i < max(0, detail_top):
            det = fetch_detail(it["link"])
            it.update(det)
            # 拿到正文后用"标题 + 正文开头"重判岗位取向：
            # 很多公告标题只写"招聘公告"，岗位类型要看正文里的岗位表。
            hit_text = f'{it["title"]} {det.get("text_head", "")}'
            role, note = role_fit(hit_text)
            it["role"], it["role_note"] = role, note
            it["priority"] = priority_of(it["title"], det.get("text_head", ""))
            it.pop("text_head", None)          # 别把正文塞进报告里

    for it in new:
        it["is_new"] = True
    for it in items:
        it.setdefault("is_new", False)

    if only_recruit:
        new = [x for x in new if x["kind"] == "招聘公告"] or new
    if tech_only:
        keep = [x for x in new if not str(x.get("role", "")).startswith("⛔")]
        new = keep or new

    if not dry_run:
        now = _dt.datetime.now().isoformat(timespec="seconds")
        for it in items:
            seen[it["id"]] = {"title": it["title"], "link": it["link"], "first_seen": now}
        save_seen(seen)

    return {
        "checked_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "new": new,
        "all": items,
        "total_seen": len(seen),
    }


def by_priority(items: list[dict]) -> list[dict]:
    """排序规则：**报名中的排最前，且离截止越近越靠前**（"别错过"是唯一指标），
    同一天数再比优先级（云南 ★★★★★ 优先）；没解析出窗口的排在报名中的最后；已结束垫底。

    故意让"紧急度"压过"优先级"：一个还剩 3 天的外省岗位，错过就是错过；
    而一个还剩 20 天的云南岗位，晚两天看也不迟。
    """
    def key(it):
        left = it.get("days_left")
        # 0=报名中(越急越前)　1=窗口没解析出来（可能还没发，值得看）　2=已结束（垫底）
        if left is None:
            bucket = 1
        elif left >= 0:
            bucket = 0
        else:
            bucket = 2
        return (bucket, left if left is not None else 9999, -it.get("priority", 0))
    return sorted(items, key=key)


def urgent(items: list[dict], within_days: int = 10) -> list[dict]:
    """正在报名、且 10 天内截止的（最需要马上投的）。"""
    out = []
    for it in items:
        left = it.get("days_left")
        if left is not None and 0 <= left <= within_days:
            out.append(it)
    return out


def as_text(result: dict = None, limit: int = 100) -> str:
    r = result or scan(detail_top=0)
    L = ["🍃 烟草招聘监控", "=" * 60, ""]
    L.append(f'扫描时间：{r["checked_at"]}　累计已见公告：{r["total_seen"]} 条　'
             f'本轮新增：{len(r["new"])} 条')
    L.append("监控源头：" + SOURCE_NAME + "（" + LIST_URLS[0] + "）")
    L.append("")
    if r["new"]:
        L.append(f'🆕 本轮新增 {len(r["new"])} 条')
        L.append("-" * 56)
        for it in by_priority(r["new"]):
            L.append(f'{stars(it["priority"])} [{it["kind"]}] {it["title"]}')
            if it.get("role"):
                L.append(f'    岗位取向：{it["role"]}　{it.get("role_note", "")}')
            L.append(f'    {it["link"]}')
            if it.get("apply_from") or it.get("apply_to"):
                L.append(f'    报名窗口：{it.get("apply_from") or "?"} ~ {it.get("apply_to") or "?"}'
                         f'（{it.get("open_days") or "?"} 天）'
                         + (f'　⏰ 还剩 {it["days_left"]} 天' if it.get("days_left") is not None else ""))
            if it.get("apply_platform"):
                L.append(f'    报名平台：{it["apply_platform"]}')
            if it.get("quota_note"):
                L.append(f'    {it["quota_note"]}')
            L.append("")
    else:
        L.append("本轮没有新增公告。")
        L.append("")
    L.append("最近公告（全部）")
    L.append("-" * 56)
    for it in by_priority(r["all"])[:limit]:
        flag = "🆕" if it.get("is_new") else "  "
        L.append(f'{flag} {stars(it["priority"])} {it.get("role", "")} {it["title"]}')
    L.append("")
    L.append("岗位取向：✅技术/管理类 = 与你专业对口，优先投；⛔一线/操作类 = 你已明确不投，只作参考；")
    L.append("          ⚠️混合 = 公告里技术和操作岗都有，进公告看岗位表再决定。")
    L.append("⚠️ 烟草铁律：同一批次只能报 1 个单位 1 个岗位，**重复投递直接取消资格**；")
    L.append("   网申窗口通常只有 7~10 天，看到公告当天就要动手。投前先在本工具「📮 网申跟踪」记一笔。")
    return "\n".join(L)
