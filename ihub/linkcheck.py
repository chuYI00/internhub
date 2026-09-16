# -*- coding: utf-8 -*-
"""链接体检 —— 只保留 A 级渠道，砍掉「伪直达」。

为什么要有这个模块
------------------
《重构指令》第 2 步的硬标准：

    ① 真实可达（HTTP 200）
    ② 打开后页面内容确实属于该企业（标题 / 域名能对上）
    ③ 是投递入口本身，不是搜索页、不是聚合平台转发页

达不到标准的不能当主按钮，要降到「其他来源」折叠区并标明来源平台。
「百度 `site:` 站内搜」这种点开只能看到百度页的，全部移除。

所以这里做两件事：

  A. **离线规则**（`is_fake_direct` / `domain_of` / `static_verdict`）
     —— 不联网就能判定的部分：域名是不是搜索引擎、是不是聚合平台转发页。
     全项目任何地方给用户展示链接前都能先过一遍，测试里也靠它做静态防线。

  B. **联网体检**（`run` / `check_url`）
     —— 真的去请求一遍，看状态码、最终域名、页面标题、正文有没有该单位关键词，
        给出 A / B / C / D 四个等级。

五个等级
--------
    A  官方直达   ：200 + 最终域名属于该单位 + 页面标题/正文能对上 + 不是平台站
                    —— **只有它能当「官方投递直达」主按钮**
    P  平台入口   ：200 + 页面确实是那个平台的，但域名是招聘平台/聚合站
                    （BOSS、智联、国聘、24365…）—— 只能进「平台入口」区，
                    不能冒充企业官方投递页
    B  可打开但弱 ：200 但需要登录 / 前端空壳 / 跳到了别的域名 —— 收进「其他来源」
    C  淘汰       ：搜索页 / 伪直达 / 死链 —— 不能给用户
    D  待本机复查 ：沙箱网络不通（TLS 拦截、超时、连接重置）或撞上站点反爬
                    （403/412/418/429）—— **这不是结论**，本机浏览器点一次即可确认

怎么用
------
    from ihub import linkcheck as lc
    lc.is_fake_direct("https://www.baidu.com/s?wd=x")     # True
    lc.static_verdict("云南中烟", "https://www.ynzy-tobacco.com/")   # ("A", "...")
    res = lc.run(workers=8)        # 联网体检全部渠道（约 1~2 分钟）
    lc.report_md(res)              # 生成 markdown 报告

命令行（推荐，会写 data/link_health.json + 链接体检报告.md）：
    python run_linkcheck.py
"""
from __future__ import annotations

import json
import os
import re
import ssl
import warnings
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

from . import config

# ─────────────────────── A. 离线规则 ───────────────────────

# 搜索引擎 / 聚合搜索类的域名：只要点在它们上面，点开看到的就是「搜索页」，
# 不是目标页面 —— 这类「伪直达」一律淘汰。
SEARCH_ENGINE_HOSTS = (
    "baidu.com", "sogou.com", "bing.com", "google.com", "so.com",
    "sm.cn", "360.cn", "yandex.com", "duckduckgo.com",
)

# 搜索引擎的查询参数特征（域名可能被短链掩盖，参数是第二道防线）
_SEARCH_QUERY_MARK = ("/s?wd=", "/s?q=", "?query=", "&query=", "?q=", "search?keyword=")

# 撞上这些状态码说明「站点在，只是挡了机器人」——不能当死链。
# 403 拒绝、405 方法不允许、412 预置条件失败（WAF）、418 我是茶壶（反爬梗）、
# 429 限频、503 人机校验。本机浏览器打开通常是正常的。
ANTIBOT_CODES = (401, 403, 405, 406, 412, 418, 429, 451, 503)

# 「平台站」——招聘信息的转发口岸，不是企业的官方投递页。
# 只在用户**明确要看平台**时保留（platforms.py 的入口本来就属于这一档），
# 当作「企业官方投递直达」按钮时必须降级成 P 级。
PLATFORM_HOSTS = (
    "zhipin.com", "zhaopin.com", "51job.com", "liepin.com", "lagou.com",
    "shixiseng.com", "yingjiesheng.com", "my.yingjiesheng.com", "nowcoder.com",
    "gaoxiaojob.com", "chinahr.com", "job1001.com", "haitou.cc", "wutongguo.com",
    "iguopin.com", "ncss.cn", "job.mohrss.gov.cn", "ynhr.com", "kmrc.com.cn",
    "maimai.cn", "zhihu.com", "linkedin.com", "bilibili.com",
)

# 企业自有的 **ATS 托管域名**（北森 / Moka / 大易 / 飞书招聘 / 智联 i.zhaopin…）。
# 这些域名不属于企业主域，但那个子域**是该企业专属的网申系统** ——
# 顺手把腾讯、字节、建投这类都接进来了，不能因为它们不是 .com 主域就降级。
ATS_HOSTS = (
    "zhiye.com",        # 北森 zhiye（云南建投 ynjstzkg.zhiye.com）
    "mokahr.com",       # Moka
    "dayee.com",        # 大易
    "feishu.cn",        # 飞书招聘（nio.jobs.feishu.cn）
    "hotjob.cn",        # 北森另一套
    "jobapply.cn", "careerqihang.com", "nowcoder.com.cn",
)


def is_ats(url: str) -> bool:
    """是不是企业专属的 ATS 网申系统子域（域名非企业主域，但仍是官方报名口径）。"""
    host = domain_of(url)
    return any(host == h or host.endswith("." + h) for h in ATS_HOSTS)


def domain_of(url: str) -> str:
    """取主机名（小写、去掉 www.）。"""
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return ""
    return host[4:] if host.startswith("www.") else host


def registrable(host: str) -> str:
    """粗略的「可注册域名」：取最后两段；常见二级后缀（.com.cn/.gov.cn 等）取三段。

    不需要绝对精确 —— 我们只用它判断「跳走没跳走」。
    """
    host = (host or "").lower()
    if not host:
        return ""
    parts = host.split(".")
    if len(parts) <= 2:
        return host
    two = ".".join(parts[-2:])
    if two in ("com.cn", "net.cn", "org.cn", "gov.cn", "edu.cn", "co.jp", "com.hk"):
        return ".".join(parts[-3:])
    return two


def is_fake_direct(url: str) -> bool:
    """是不是「伪直达」（点开只能看到搜索页）。

    这是全项目的硬规则：**任何以「官方投递 / 直达」名义展示的链接，都不能是它**。
    """
    if not url:
        return False
    u = url.lower()
    host = domain_of(u)
    if any(host == h or host.endswith("." + h) for h in SEARCH_ENGINE_HOSTS):
        return True
    # 域名被短链/中转掩盖时，靠「搜索引擎域名 + 查询参数」双条件兜底
    if any(engine in u for engine in ("baidu.com", "sogou.com", "bing.com")):
        if any(mark in u for mark in _SEARCH_QUERY_MARK):
            return True
    return False


def is_platform(url: str) -> bool:
    """是不是招聘平台/聚合站（不是企业官方页）。"""
    host = domain_of(url)
    return any(host == h or host.endswith("." + h) for h in PLATFORM_HOSTS)


def is_any_search(url: str) -> bool:
    """宽口径：伪直达 or 平台站 —— 「不能当企业官方投递按钮」。"""
    return is_fake_direct(url) or is_platform(url)


def can_be_official_button(url: str) -> bool:
    """这条链接**能不能**当「官方投递直达」主按钮。

    硬规则：不是伪直达、不是平台站 —— 也就是必须落在企业/单位自己的域名上。
    网页里给主按钮前应该先过一遍这个函数。
    """
    if not url:
        return False
    return not is_any_search(url)


def _words_hit(text: str, words) -> str:
    """页面里命中哪个关键词（英文不区分大小写）。"""
    if not words:
        return ""
    low = (text or "").lower()
    for w in words:
        if w and w.lower() in low:
            return w
    return ""


def static_verdict(label: str, url: str, words=None) -> tuple[str, str]:
    """离线判定（不联网）。返回 (等级, 原因)。

    - 能判死的直接判死（C：伪直达、非法网址）。
    - 平台站先记一笔（不要当官方按钮，但联网后可能升/降），返回 ("P?", ...)。
    - 其余返回 ("?", "需联网体检")，交给 `check_url` + `net_verdict` 定级。
    """
    if not url:
        return "C", "空链接"
    if is_fake_direct(url):
        return "C", "伪直达（点开只是搜索引擎结果页）"
    host = domain_of(url)
    if not host:
        return "C", "不是合法网址"
    if not url.startswith(("http://", "https://")):
        return "C", "缺少 http(s) 前缀"
    if is_platform(url):
        return "P?", "招聘平台/聚合站 —— 只能当平台入口，不能当企业官方投递页"
    return "?", "需联网体检"


def net_verdict(label: str, url: str, checked: dict, words=None,
                expect_host_ok=None) -> tuple[str, str]:
    """把一次联网体检的结果翻译成等级。

    checked 来自 `check_url`：{status, final_url, title, body_len, error, ...}
    """
    if not checked or checked.get("error"):
        return "D", f"沙箱测不了（{checked.get('error', '无结果')}）—— 本机浏览器点一次即可确认"

    st = checked.get("status") or 0
    final = checked.get("final_url") or url
    title = (checked.get("title") or "").strip()
    body_len = int(checked.get("body_len") or 0)
    blob = f"{title} {checked.get('snippet') or ''}"

    if st in ANTIBOT_CODES:
        return "D", f"站点反爬（HTTP {st}，站是活的）—— 本机浏览器能打开，需你点一次确认"
    if st >= 400 or st == 0:
        return "C", f"打不开（HTTP {st}）"
    if 300 <= st < 400:
        return "C", f"死循环跳转（HTTP {st}）"

    # 跳到别的站（尤其是跳到搜索引擎 / 平台站）→ 这条链接就不是它自称的那个页面
    hopped = registrable(domain_of(final)) != registrable(domain_of(url))
    if hopped:
        if is_fake_direct(final):
            return "C", f"实际跳到了搜索引擎（{domain_of(final)}）"
        if is_platform(final):
            return "P", f"实际跳到了招聘平台（{domain_of(final)}）—— 不是企业官方页"
        return "B", f"跳到了别的域名（{domain_of(url)} → {domain_of(final)}）"

    if is_fake_direct(final):
        return "C", "落点仍是搜索引擎页"

    # 域名一致 + 200：这条链接「落点是对的」。剩下只需要判断页面是不是这家单位的。
    shell = body_len < 900 and re.search(
        r"(enable javascript|<div id=\"app\"|<div id=\"root\"|loading|正在加载|请开启)",
        f"{checked.get('snippet') or ''} {title}", re.I)
    if shell:
        # 北森/Moka/飞书这类企业 ATS 全是前端渲染，沙箱只能拿到空壳 ——
        # 这不是「链接有问题」，是这一侧看不到内容，交给本机浏览器确认。
        base = "企业专属 ATS 网申系统" if is_ats(url) else "前端渲染（JS 应用）"
        return "D", f"HTTP {st}｜域名一致｜{base}，沙箱只拿到空壳 —— 本机浏览器正常"

    hit = _words_hit(blob, words)
    if words and not hit:
        if body_len < 600:
            return "D", f"HTTP {st}｜域名一致｜页面过少（{body_len} 字节），疑前端渲染，需本机确认"
        if is_platform(url):
            return "P", f"平台页，但页面上找不到「{label}」相关内容（{len(words)} 个关键词都没命中）"
        return "B", f"HTTP {st}｜域名一致，但标题/正文里找不到该单位关键词（{len(words)} 个都没命中）"
    if body_len < 400:
        return "D", f"HTTP {st}｜域名一致｜页面几乎是空壳（{body_len} 字节），需本机确认"
    if re.search(r"(请登录|登录后查看|立即登录|用户登录)", title):
        return "B", "落地页是登录页"

    tag = f"｜页面含「{hit}」" if hit else ""
    if is_platform(url):
        return "P", f"HTTP {st}｜平台站入口（非企业官方页）{tag}"
    if is_ats(url):
        return "A", f"HTTP {st}｜企业专属 ATS 网申系统（域名非企业主域）{tag}"
    return "A", f"HTTP {st}｜域名一致｜企业/单位官方域名{tag}"


# ─────────────────────── B. 联网体检 ───────────────────────

# 每个来源域名的「关键词指纹」：页面里出现其中任意一个，才算「内容属于该单位」。
# 只给**重要且容易判错**的加，其余用公司名字段自动兜底。
HOST_WORDS = {
    "tobacco.gov.cn": ("烟草", "专卖局", "中烟"),
    "ynzy-tobacco.com": ("中烟", "烟草", "红云红河", "红塔"),
    "zhaopin.csg.cn": ("南方电网", "电网", "招聘"),
    "cnyeig.com": ("能投", "能源投资"),
    "ynairport.com": ("机场", "航空产业投资", "招聘"),
    "ynjstzkg.zhiye.com": ("建投", "建设投资"),
    "ynjstzkg.com": ("建投", "建设投资"),
    "job.ceair.com": ("东方航空", "东航", "招聘"),
    "job.csair.com": ("南方航空", "南航", "招聘"),
    "caac.gov.cn": ("民用航空", "民航局"),
    "job.10086.cn": ("中国移动", "移动", "招聘"),
    "job.chinatelecom.com.cn": ("中国电信", "电信", "招聘"),
    "zhaopin.chnenergy.com.cn": ("国家能源", "招聘"),
    "career.huawei.com": ("华为", "Huawei"),
    "job.zte.com.cn": ("中兴", "ZTE"),
    "cimc.com": ("中集", "CIMC"),
    "yunnanbaiyao.com.cn": ("云南白药", "白药"),
    "firstcapital.com.cn": ("第一创业",),
    "job.icbc.com.cn": ("工商银行", "工行", "ICBC"),
    "career.abchina.com": ("农业银行", "农行", "ABC"),
    "job2.ccb.com": ("建设银行", "建行", "CCB"),
    "campus.chinahr.com": ("中国银行", "招聘"),
    "job.bankcomm.com": ("交通银行", "交行"),
    "career.psbc.com": ("邮储银行", "邮政储蓄", "邮储"),
    "ynrcc.com": ("农村信用社", "农信社", "农信"),
    "campus.pingan.com": ("平安", "招聘"),
    "jobs.bytedance.com": ("字节跳动", "ByteDance"),
    "jobs.feishu.cn": ("蔚来", "NIO"),
    "iguopin.com": ("国聘", "招聘"),
    "job.ncss.cn": ("就业", "招聘", "24365"),
    "job.mohrss.gov.cn": ("招聘", "人力资源"),
    "zhipin.com": ("BOSS", "直聘", "招聘"),
    "xiaoyuan.zhaopin.com": ("智联", "校园招聘", "招聘"),
    "51job.com": ("前程无忧", "51job", "招聘"),
    "liepin.com": ("猎聘", "招聘"),
    "shixiseng.com": ("实习僧", "招聘"),
    "yingjiesheng.com": ("应届生", "招聘"),
    "nowcoder.com": ("牛客", "招聘"),
    "gaoxiaojob.com": ("高校人才网", "人才", "招聘"),
    "ynhr.com": ("云南人才", "招聘"),
    "hrss.yn.gov.cn": ("人力资源", "社会保障", "云南"),
    "jyt.yn.gov.cn": ("教育厅", "云南", "教育"),
    "rsj.km.gov.cn": ("昆明", "人力资源", "社会保障"),
    "hrss.dali.gov.cn": ("大理", "人力资源", "社会保障"),
    "dali.gov.cn": ("大理", "人民政府"),
    "cauc.bysjy.com.cn": ("中国民航大学", "就业", "招聘"),
    "job.kmust.edu.cn": ("昆明理工", "就业", "招聘"),
    "dldx.jysd.com": ("大理大学", "就业", "招聘"),
    "kmrc.com.cn": ("昆明人才", "招聘"),
    "boc.cn": ("中国银行", "招聘"),
    "psbc.com": ("邮储银行", "邮政储蓄"),
    "pgcareers.com": ("P&G", "Procter", "宝洁", "career"),
    "china-railway.com.cn": ("铁路", "人才", "招聘"),
    "81rc.81.cn": ("军队", "文职", "人才"),
    "bjbys.net.cn": ("北京", "毕业生", "就业"),
    "sgcc.com.cn": ("国家电网", "电网", "招聘"),
    "cnpc.com.cn": ("石油", "招聘"),
    "yunnanbaiyao.com.cn": ("云南白药", "白药"),
    "gzw.yn.gov.cn": ("国资", "云南"),
    "weifang.gov.cn": ("潍坊", "人力资源"),
    "shandong.gov.cn": ("山东", "就业", "人才"),
    "dldx.jysd.com": ("大理大学", "就业", "招聘"),
    "jysd.com": ("就业", "招聘", "校园"),
    "bysjy.com.cn": ("就业", "招聘", "校园"),
}


# 关键词里不能拿来当「指纹」的通用词 —— 命中了也说明不了问题
_STOP_WORDS = {"招聘", "校园", "官方", "平台", "信息网", "就业网", "网络", "系统", "专栏",
               "资源", "服务", "中心", "渠道", "入口", "公众号", "搜索"}


def words_for(url: str, label: str = "") -> tuple:
    """给一条链接配「页面里应该出现什么词」的指纹。

    优先用人工维护的 HOST_WORDS；没有就从标签里切 n-gram 兜底
    （切太粗会误判 —— 曾把「中国银行招聘公告」整串当关键词，永远命不中）。
    """
    host = domain_of(url)
    out = list(HOST_WORDS.get(host, ()))
    for h, ws in HOST_WORDS.items():          # 允许子域命中（rb.hrss.yn.gov.cn）
        if not out and host.endswith("." + h):
            out = list(ws)
    if out:
        return tuple(dict.fromkeys(out))

    if not label:
        return ()
    core = re.split(r"[·（(]", label)[0]              # 去掉「·站内搜索」这类后缀
    core = re.sub(r"[A-Za-z0-9\s]", "", core)         # 去掉英文数字
    cjk = "".join(re.findall(r"[\u4e00-\u9fa5]", core))
    grams = []
    for n in (4, 3, 2):                               # 由长到短，长的更准
        for i in range(len(cjk) - n + 1):
            g = cjk[i:i + n]
            if g not in _STOP_WORDS:
                grams.append(g)
    grams = [g for g in dict.fromkeys(grams) if g not in _STOP_WORDS]
    return tuple(grams[:24])


def _decode(r) -> str:
    """把响应体解成字符串：优先响应头里的 charset，没有就嗅探（国内站多为 GBK）。"""
    ct = (r.headers.get("Content-Type") or "").lower()
    enc = r.encoding
    if "charset=" not in ct:
        raw = r.content[:300000]
        enc = ""
        import re as _re
        m = _re.search(rb'charset\s*=\s*["\']?([\w-]+)', raw[:4000], _re.I)
        if m:
            enc = m.group(1).decode("ascii", "ignore")
        if not enc:
            try:
                from charset_normalizer import from_bytes
                best = from_bytes(raw).best()          # 大多数情况能认出 gb2312
                enc = best.encoding if best else ""
            except Exception:
                enc = ""
        enc = enc or r.apparent_encoding or "utf-8"
    try:
        return r.content.decode(enc, errors="replace")
    except (LookupError, TypeError):
        return r.text or ""


def check_url(url: str, timeout: int = 12, retries: int = 1) -> dict:
    """真去请求一次，拿状态码 / 最终地址 / 标题 / 正文长度。

    沙箱里很多站会被 TLS 拦截或连接重置 —— 这不算「死链」，只标 D（待本机复查）。
    """
    try:
        import requests
    except Exception as e:  # pragma: no cover
        return {"url": url, "error": f"没有 requests：{e}"}

    warnings.filterwarnings("ignore")
    last = ""
    for _ in range(retries + 1):
        try:
            s = requests.Session()
            s.trust_env = False                       # 绕开沙箱里那个已经关掉的代理
            r = s.get(url, timeout=timeout, verify=False, allow_redirects=True,
                      headers={"User-Agent": config.USER_AGENT,
                               "Accept-Language": "zh-CN,zh;q=0.9"})
            # 大量国内政府/企业站是 GBK 且响应头不带 charset，requests 会猜成
            # ISO-8859-1 → 全页乱码 → 关键词永远命不中。这里显式纠一次编码。
            body = _decode(r)
            m = re.search(r"<title[^>]*>(.*?)</title>", body, re.S | re.I)
            title = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
            text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", body, flags=re.S | re.I)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text)
            return {
                "url": url, "status": r.status_code, "final_url": r.url,
                "title": title[:200], "body_len": len(text),
                "snippet": text[:1200], "error": "",
            }
        except Exception as e:
            last = f"{type(e).__name__}: {str(e)[:70]}"
    return {"url": url, "error": last}


# ─────────────────────── C. 汇总项目里的所有链接 ───────────────────────

def collect_targets() -> list[dict]:
    """把项目里所有「会给用户点」的链接汇总成待体检清单。

    返回 [{"label","url","where","words"}]，已按 URL 去重。
    """
    from . import channels, platforms, yunnan, campus_channels

    seen: dict[str, dict] = {}

    def add(label, url, where):
        url = (url or "").strip()
        if not url.startswith("http"):
            return                     # 渠道清单里有些条目只是「提醒」文字，不是链接
        if url in seen:
            return
        seen[url] = {"label": label, "url": url, "where": where,
                     "words": list(words_for(url, label))}

    for company, url in channels.OFFICIAL_URLS.items():
        add(company, url, "channels（企业官方招聘入口）")

    for p in platforms.all_platforms():
        add(p["name"].split("（")[0], p["url"], "platforms（平台入口矩阵）")
        extra = platforms.in_site_search(p)
        if extra:
            add(p["name"].split("（")[0] + "·站内搜索", extra, "platforms（站内搜索）")

    for u in yunnan.all_units():
        add(u["name"], u.get("portal", ""), "yunnan（官方公告页）")
        add(u["name"] + "·网申", u.get("apply", ""), "yunnan（网申入口）")

    for title, items in campus_channels.CHANNEL_GROUPS:
        for name, url in items:
            add(name, url, f"campus_channels（{title}）")

    return list(seen.values())


def run(workers: int = 8, only=None, targets=None) -> list[dict]:
    """联网体检。only 可传域名关键字过滤（调试用）。"""
    targets = targets or collect_targets()
    if only:
        targets = [t for t in targets if any(o in t["url"] for o in only)]

    def one(t):
        st, reason = static_verdict(t["label"], t["url"], t.get("words"))
        if st == "C":
            return {**t, "grade": "C", "reason": reason, "checked": None,
                    "official": False}
        checked = check_url(t["url"])
        g, why = net_verdict(t["label"], t["url"], checked, t.get("words"))
        return {**t, "grade": g, "reason": why, "checked": checked,
                "official": g == "A"}

    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(one, targets))


def load_saved() -> list[dict]:
    """读上一次体检结果（没有就返回空）。"""
    p = os.path.join(config.DATA_DIR, "link_health.json")
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f).get("results", [])
    except Exception:
        return []


def saved_at() -> str:
    """上次体检时间。"""
    p = os.path.join(config.DATA_DIR, "link_health.json")
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f).get("checked_at", "")
    except Exception:
        return ""


def save(results: list[dict]) -> str:
    os.makedirs(config.DATA_DIR, exist_ok=True)
    p = os.path.join(config.DATA_DIR, "link_health.json")
    from datetime import datetime
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"checked_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                   "results": results}, f, ensure_ascii=False, indent=2)
    return p


# ─────────────────────── D. 报告 ───────────────────────

GRADE_TITLE = {
    "A": "A 级 · 官方直达（可以当「官方投递」主按钮）",
    "P": "P 级 · 平台入口（站是好的，但不是企业官方页 —— 只能当平台入口）",
    "B": "B 级 · 可打开但信息不足（收进「其他来源」折叠区）",
    "C": "C 级 · 淘汰（伪直达 / 死链）",
    "D": "D 级 · 待本机复查（沙箱网络不通或撞反爬，不是结论）",
}

GRADE_ORDER = ("A", "P", "B", "C", "D")


def summary(results: list[dict]) -> dict:
    out = {g: 0 for g in GRADE_ORDER}
    for r in results:
        out[r["grade"]] = out.get(r["grade"], 0) + 1
    out["total"] = len(results)
    return out


def report_md(results: list[dict], checked_at: str = "") -> str:
    s = summary(results)
    L = ["# 渠道链接体检报告", ""]
    L.append(f"- 体检时间：{checked_at or '—'}")
    L.append(f"- 受检链接：**{s['total']} 条** ｜ "
             + " ｜ ".join(f"{g} {s[g]}" for g in GRADE_ORDER))
    L.append("")
    L.append("> 判定标准（《重构指令》第 2 步）：链接真实可达（HTTP 200）、打开后页面确实属于该单位、"
             "且是投递入口本身 —— 不是搜索页、不是平台转发页。")
    L.append("> **只有 A 级能当「官方投递直达」主按钮**；P 级是招聘平台自己的入口（BOSS/智联/国聘…），"
             "信息是真的但页不属于那家企业，只能放「平台入口」区。")
    L.append("> D 级不是失败：沙箱里被 TLS 拦截 / 连接重置 / 撞上反爬（403·412·418）的站，"
             "本机浏览器通常正常，**需要你点一次确认**。")
    L.append("")
    for g in GRADE_ORDER:
        rows = [r for r in results if r["grade"] == g]
        if not rows:
            continue
        L.append(f"## {GRADE_TITLE[g]}（{len(rows)} 条）")
        L.append("")
        L.append("| 单位 / 入口 | 链接 | 出处 | 判定依据 |")
        L.append("|---|---|---|---|")
        for r in sorted(rows, key=lambda x: x["label"]):
            L.append(f"| {r['label']} | `{r['url']}` | {r['where'].split('（')[0]} | {r['reason']} |")
        L.append("")
    L.append("---")
    L.append("")
    L.append("重新体检：`venv\\Scripts\\python.exe run_linkcheck.py`（会覆盖本报告与 data/link_health.json）")
    return "\n".join(L)
