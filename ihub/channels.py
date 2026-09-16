# -*- coding: utf-8 -*-
"""企业官方招聘渠道映射。

说明：
- OFFICIAL_URLS：内置常用企业官方招聘入口（已核验的才放）。
- 用户可在 data/official_urls.json 里覆盖/新增，格式 {"公司名": "https://..."}，
  覆盖优先级高于内置表。
- 未收录的公司 official_url 为空，界面会显示“—”，可按上文方法自行补充。
"""
import json
import os

from . import config

# 仅收录确认可用的官方入口。
# 标注 [实测] = 2026-09 沙箱内直接请求返回 200；
#      [一手] = 该地址是从抓到的招聘公告里解出来的官方网申入口（沙箱 TLS 拦了银行站，浏览器可开）。
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
    "中国银行": "https://campus.chinahr.com/pages/boc/",                     # [实测]
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


def official_for(company: str) -> str:
    if not company:
        return ""
    merged = dict(OFFICIAL_URLS)
    merged.update(_user_overrides())
    # 1) 精确名
    if company in merged:
        return merged[company]
    # 2) 包含匹配，但取「命中的最长公司名」——
    #    否则「云南红塔银行」会先撞上「红塔集团」这种更短的键，配到错的官网。
    best_key, best_len = "", 0
    for key in merged:
        if not key:
            continue
        if (key in company or company in key) and len(key) > best_len:
            best_key, best_len = key, len(key)
    return merged.get(best_key, "")
