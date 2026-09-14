# -*- coding: utf-8 -*-
"""秋招信息渠道（按用户提供的七大板块整理）+ 各渠道"搜索直达"链接生成。

说明：这里只提供**官方/公开入口**与**搜索直达链接**，不代替登录抓取；
岗位信息以各平台/官网公告为准。
"""
from urllib.parse import quote

# 七大板块：(板块标题, [(名称, 链接), ...])
CHANNEL_GROUPS = [
    ("🏛️ 国家级官方平台（权威性最高）", [
        ("国家大学生就业服务平台 24365（教育部）", "https://job.ncss.cn"),
        ("24365 主站", "https://www.ncss.cn"),
        ("国聘网（国资委+教育部+人社部）", "https://www.iguopin.com"),
        ("国聘·国资央企招聘专区", "https://cujiuye.iguopin.com"),
        ("国聘·校招频道", "https://xiaoyuan.iguopin.com"),
        ("中国公共招聘网（人社部）", "http://job.mohrss.gov.cn"),
        ("国资委官网·人事专栏", "http://www.sasac.gov.cn"),
        ("国资小新（公众号 guozixiaoxin）", "https://www.baidu.com/s?wd=" + quote("国资小新 央企 校招")),
        ("工信部中小企业百日招聘（中国中小企业服务网）", "https://www.chinasme.cn"),
    ]),
    ("🏫 校园专属渠道（竞争压力最小）", [
        ("中国民航大学就业信息网", "https://www.cauc.edu.cn"),
        ("海投网（宣讲会/双选会汇总）", "https://www.haitou.cc"),
        ("应届生求职网（宣讲会日历/面经）", "https://www.yingjiesheng.com"),
        ("梧桐果（宣讲会）", "https://www.wutongguo.com"),
    ]),
    ("💼 综合招聘平台（覆盖面广，海投初筛）", [
        ("应届生求职网", "https://www.yingjiesheng.com"),
        ("智联招聘·校园", "https://xiaoyuan.zhaopin.com"),
        ("前程无忧 51job", "https://www.51job.com"),
        ("BOSS直聘", "https://www.zhipin.com"),
        ("实习僧（实习/校招）", "https://www.shixiseng.com"),
        ("猎聘·校园", "https://campus.liepin.com"),
        ("拉勾网", "https://www.lagou.com"),
        ("中华英才网", "https://www.chinahr.com"),
    ]),
    ("🎯 行业垂直渠道（针对性强）", [
        ("牛客网（技术岗/内推/面经）", "https://www.nowcoder.com"),
        ("中国银行招聘公告", "https://www.boc.cn/aboutboc/bi4/"),
        ("工商银行招聘", "https://job.icbc.com.cn"),
        ("农业银行招聘", "https://career.abchina.com.cn"),
        ("建设银行招聘", "https://job2.ccb.com"),
        ("交通银行招聘", "https://job.bankcomm.com"),
        ("邮储银行招聘", "https://www.psbc.com/cn/gyyc/rczp/xyzp/"),
        ("国家电网招聘", "https://zhaopin.sgcc.com.cn"),
        ("中石油招聘", "https://zhaopin.cnpc.com.cn"),
        ("中国铁路人才网（18 个铁路局唯一官方）", "https://rczp.china-railway.com.cn"),
        ("军队人才网（文职唯一官方）", "http://81rc.81.cn"),
    ]),
    ("🗺️ 地方性渠道（回省/下沉就业）", [
        ("云南省人力资源和社会保障厅", "https://hrss.yn.gov.cn"),
        ("大理州人民政府（本地公告）", "https://www.dali.gov.cn"),
        ("云南省国资委", "https://gzw.yn.gov.cn"),
        ("山东人社·乐业山东", "https://hrss.shandong.gov.cn"),
        ("潍坊市人力资源和社会保障局", "https://rsj.weifang.gov.cn"),
        ("北京高校大学生就业创业信息网", "https://www.bjbys.net.cn"),
    ]),
    ("🤝 内推与社交渠道（提高通过率）", [
        ("牛客网·内推帖", "https://www.nowcoder.com"),
        ("脉脉（学长学姐内推）", "https://maimai.cn"),
        ("LinkedIn 领英（外企/校友）", "https://www.linkedin.com"),
        ("OfferShow 内推群（搜索）", "https://www.baidu.com/s?wd=" + quote("OfferShow 内推群 校招")),
    ]),
    ("📢 社群与信息聚合（信息差）", [
        ("校招信息管理平台（offer情报局）", "https://offerqingbaoju.cn"),
        ("2027秋招企业汇总表（givemeoc）", "https://www.givemeoc.com"),
        ("2027届秋招国企汇总（百度直达）", "https://www.baidu.com/s?wd=" + quote("2027届 秋招 国企 汇总表")),
        ("知乎（求职经验/内推）", "https://www.zhihu.com"),
    ]),
]

# 便于"搜索直达"的平台（用百度站内/关键词方式，无需登录也能看到公告）
SEARCH_SITES = [
    ("国聘（iguopin）", "site:iguopin.com"),
    ("24365 国家大学生就业服务平台", "site:ncss.cn"),
    ("中国公共招聘网", "site:job.mohrss.gov.cn"),
    ("实习僧", "site:shixiseng.com"),
    ("智联招聘", "site:zhaopin.com"),
    ("前程无忧", "site:51job.com"),
    ("BOSS直聘", "site:zhipin.com"),
    ("牛客网", "site:nowcoder.com"),
    ("应届生求职网", "site:yingjiesheng.com"),
    ("高校就业信息网（.edu.cn）", "site:edu.cn"),
]


def search_links(city: str = "", keyword: str = "", year: str = "2027届") -> list:
    """生成"城市+关键词+秋招"在各平台的搜索直达链接（供网页展示）。"""
    parts = [p for p in [year, "秋招", "校园招聘", city, keyword] if p]
    q = " ".join(parts)
    out = [("百度（全网）", f"https://www.baidu.com/s?wd={quote(q)}")]
    for name, site in SEARCH_SITES:
        out.append((f"{name} 搜索", f"https://www.baidu.com/s?wd={quote(site + ' ' + q)}"))
    out.append(("B站（备考/经验）", f"https://search.bilibili.com/all?keyword={quote(q + ' 笔试 面试')}"))
    return out
