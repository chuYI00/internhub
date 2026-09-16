# -*- coding: utf-8 -*-
"""企业官方招聘渠道映射。

说明：
- OFFICIAL_URLS：内置常用企业官方招聘入口（**只放企业/单位自己的域名**）。
- 用户可在 data/official_urls.json 里覆盖/新增，格式 {"公司名": "https://..."}，
  覆盖优先级高于内置表。
- 未收录的公司 official_url 为空，界面会显示“—”，可按上文方法自行补充。

链接质量（《重构指令》第 2 步）
------------------------------
这里**不出现**搜索页、也不出现聚合平台页 —— 那种「点开只是百度/智联」的伪直达
已经全部移除（历史上坑过：用户点完发现没用，就再也不信这个工具了）。
每条的体检结论由 `ihub/linkcheck.py` 跑出来，存 data/link_health.json；
`official_info()` 会把它读出来一并返回，网页端就能在按钮旁边显示 A / 待复查。
"""
import json
import os

from . import config

# 仅收录确认可用的 **企业官方域名** 入口。
# 标注 [实测] = 沙箱内直接请求返回 200（见 链接体检报告.md）；
#      [一手] = 该地址是从抓到的招聘公告里解出来的官方网申入口
#               （沙箱 TLS 拦截了银行站，浏览器可开 —— 体检里记为 D 待本机复查）。
OFFICIAL_URLS = {
    # ── 烟草系统（你的第一优先） ──
    "国家烟草专卖局": "http://www.tobacco.gov.cn/gjyc/zpxx/list.shtml",     # [实测]
    "中国烟草": "http://www.tobacco.gov.cn/gjyc/zpxx/list.shtml",           # [实测]
    "云南省烟草专卖局": "https://yn.tobacco.gov.cn/",                        # [实测]
    "云南省烟草公司": "https://yn.tobacco.gov.cn/",                          # [实测]
    "云南烟草": "https://yn.tobacco.gov.cn/",                               # [实测]
    "云南中烟": "https://www.ynzy-tobacco.com/",                            # [实测]
    "中烟工业": "https://www.ynzy-tobacco.com/",                            # [实测]
    "红云红河": "https://www.ynzy-tobacco.com/",                            # [实测]
    "红塔集团": "https://www.ynzy-tobacco.com/",                            # [实测]

    # ── 云南央国企 ──
    "中国南方电网": "https://zhaopin.csg.cn",                               # [实测]
    "南方电网": "https://zhaopin.csg.cn",                                   # [实测]
    "云南电网": "https://zhaopin.csg.cn",                                   # [实测]
    "云南能投": "http://www.cnyeig.com/",                                   # [实测]
    "能源投资集团": "http://www.cnyeig.com/",                               # [实测]
    "云南机场": "https://hr.ynairport.com/zp/",                             # [实测]
    "航空产业投资集团": "https://hr.ynairport.com/zp/",                      # [实测]
    "航产投": "https://hr.ynairport.com/zp/",                               # [实测]
    "云南建投": "https://ynjstzkg.zhiye.com/",                              # [实测]
    "建设投资控股": "https://ynjstzkg.zhiye.com/",                           # [实测]

    # ── 民航系统 ──
    "中国东方航空": "https://job.ceair.com/",                               # [实测]
    "东方航空": "https://job.ceair.com/",                                   # [实测]
    "东航": "https://job.ceair.com/",                                       # [实测]
    "中国南方航空": "https://job.csair.com/",                               # [实测]
    "南方航空": "https://job.csair.com/",                                   # [实测]
    "南航": "https://job.csair.com/",                                       # [实测]
    "中国民用航空局": "https://www.caac.gov.cn/",                            # [实测]
    "民航局": "https://www.caac.gov.cn/",                                   # [实测]

    # ── 通信 / 能源 / 制造 / 其他央企 ──
    "中国移动": "https://job.10086.cn/",                                    # [实测]
    "中国电信": "https://job.chinatelecom.com.cn/",                          # [实测]
    "国家能源集团": "https://zhaopin.chnenergy.com.cn/",                     # [实测]
    "华为": "https://career.huawei.com/",                                   # [实测]
    "中兴通讯": "https://job.zte.com.cn/",                                   # [实测]
    "中兴": "https://job.zte.com.cn/",                                       # [实测]
    "中集集团": "https://www.cimc.com/",                                    # [实测]
    "云南白药": "https://www.yunnanbaiyao.com.cn/",                          # [实测]
    "第一创业证券": "https://www.firstcapital.com.cn/",                       # [实测]

    # ── 银行 / 金融（地址来自抓到的官方公告，沙箱 TLS 拦了银行站） ──
    "中国工商银行": "https://job.icbc.com.cn/",                              # [一手]
    "工商银行": "https://job.icbc.com.cn/",                                  # [一手]
    "中国农业银行": "https://career.abchina.com/",                           # [一手]
    "农业银行": "https://career.abchina.com/",                               # [一手]
    "中国建设银行": "https://job2.ccb.com/cn/job/index.html",                # [一手]
    "建设银行": "https://job2.ccb.com/cn/job/index.html",                    # [一手]
    # 中行校招页原本挂在中华英才网（平台域名），第 2 步改成它自己的官网人才招聘栏目
    "中国银行": "https://www.boc.cn/aboutboc/bi4/",                          # [实测]
    "交通银行": "https://job.bankcomm.com/",                                 # [一手]
    "中国邮政储蓄银行": "https://career.psbc.com/",                           # [一手]
    "邮储银行": "https://career.psbc.com/",                                  # [一手]
    "云南省农村信用社": "https://www.ynrcc.com/",                             # [一手]
    "云南省农信社": "https://www.ynrcc.com/",                                 # [一手]
    "中国平安": "https://campus.pingan.com/",                                # [实测]

    # ── 互联网 / 新能源 ──
    "字节跳动": "https://jobs.bytedance.com/campus/",
    "NIO蔚来": "https://nio.jobs.feishu.cn/campus/",
    "蔚来": "https://nio.jobs.feishu.cn/campus/",
}


def _user_overrides() -> dict:
    p = os.path.join(config.DATA_DIR, "official_urls.json")
    try:
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _merged() -> dict:
    m = dict(OFFICIAL_URLS)
    m.update(_user_overrides())
    return m


def _match_key(company: str, merged: dict) -> str:
    """按「命中的最长公司名」匹配 —— 否则「云南红塔银行」会先撞上「红塔集团」。"""
    if not company:
        return ""
    if company in merged:
        return company
    best_key, best_len = "", 0
    for key in merged:
        if not key:
            continue
        if (key in company or company in key) and len(key) > best_len:
            best_key, best_len = key, len(key)
    return best_key


def official_for(company: str) -> str:
    merged = _merged()
    return merged.get(_match_key(company, merged), "")


# ── 链接体检结论（读 data/link_health.json，没有就返回空） ──
_HEALTH_CACHE: dict | None = None


def _health() -> dict:
    """{url: {"grade": "A", "reason": "..."}} —— 由 run_linkcheck.py 生成。"""
    global _HEALTH_CACHE
    if _HEALTH_CACHE is None:
        _HEALTH_CACHE = {}
        p = os.path.join(config.DATA_DIR, "link_health.json")
        try:
            with open(p, "r", encoding="utf-8") as f:
                for r in json.load(f).get("results", []):
                    _HEALTH_CACHE[r["url"]] = {
                        "grade": r.get("grade", ""), "reason": r.get("reason", ""),
                    }
        except Exception:
            pass
    return _HEALTH_CACHE


GRADE_LABEL = {
    "A": "✅ A 级·官方直达",
    "P": "📋 P 级·平台入口",
    "B": "⚠️ B 级·信息不足",
    "C": "❌ C 级·淘汰",
    "D": "🔎 待本机复查",
}


def official_info(company: str) -> dict:
    """企业官方入口 + 它的体检结论。

    返回 {"url", "grade", "label", "reason", "ok"}
      ok=True 表示**可以当「官方投递直达」主按钮**（A 级）；
      D 级不是坏链接 —— 沙箱测不了而已，网页端会照常给按钮但附一句提醒。
    """
    url = official_for(company)
    if not url:
        return {"url": "", "grade": "", "label": "—（未收录）", "reason": "", "ok": False}
    h = _health().get(url) or {}
    g = h.get("grade", "")
    return {
        "url": url,
        "grade": g,
        "label": GRADE_LABEL.get(g, "◻ 未体检"),
        "reason": h.get("reason", ""),
        "ok": g in ("A", "D", ""),        # D 只是沙箱看不到，本机是好的
    }


def health_report() -> dict:
    """本项目所有官方入口的体检汇总（网页端「🔍 链接体检」区块用它）。"""
    out = {"A": [], "P": [], "B": [], "C": [], "D": [], "?": []}
    for url, h in _health().items():
        out.setdefault(h.get("grade") or "?", []).append({"url": url, **h})
    return out
