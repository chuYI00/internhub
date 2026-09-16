# -*- coding: utf-8 -*-
"""秋招信息渠道全集（按七大板块整理）—— 只给官方入口，不给伪直达。

第 2 步重构（《重构指令》）动了什么
----------------------------------
原来这里有两样「看着很贴心、其实没用」的东西：

  1. `wx(...)` —— 搜狗微信搜索链接。点开是**搜狗的结果页**，不是公众号本身。
  2. `bd(...)` / `SEARCH_SITES` —— 一堆 `site:xxx.com 昆明 秋招` 的百度链接。
     点开是**百度的结果页**，不是岗位页；用户还得在结果里再点一次。

两类都是「伪直达」：用户点完发现没用，就再也不信这个工具了 —— 所以全部删掉。
换成的做法是：**给真入口 + 写清楚进去以后敲什么词**。
「搜索」这件事本身没错，错的是把它包装成直达。

对外接口：
    official_entries()     所有官方/公开入口（真能点开的）
    manual_search_notes()  站内搜索说明（不给链接，只给关键词与位置）
    CHANNEL_GROUPS         渠道分组（url 为空串的是纯说明条目）
"""
from urllib.parse import quote


def wx(kw: str) -> str:
    """【已废弃】搜狗微信搜索链接 —— 点开是搜索引擎页，不是公众号。仅保留供兼容。"""
    return "https://weixin.sogou.com/weixin?type=2&query=" + quote(kw)


def bd(kw: str) -> str:
    """【已废弃】百度搜索链接 —— 伪直达。新代码不要再用它当「直达」。"""
    return "https://www.baidu.com/s?wd=" + quote(kw)


CHANNEL_GROUPS = [
    ("🏫 本校与目标院校就业网（直达栏目，最该盯）", [
        ("中国民航大学·招聘信息", "https://cauc.bysjy.com.cn/module/careers?menu_id=28135"),
        ("中国民航大学·在线招聘", "https://cauc.bysjy.com.cn/module/onlines?menu_id=28135"),
        ("中国民航大学·校内双选会", "https://cauc.bysjy.com.cn/module/jobfairs?type=1&menu_id=28135"),
        ("中国民航大学·校外宣讲会", "https://cauc.bysjy.com.cn/module/careers?type=outer&menu_id=28135"),
        ("中国民航大学·学院招聘信息", "https://cauc.bysjy.com.cn/module/similar_careers?panel_type=23&menu_id=28135"),
        ("中国民航大学·通知公告", "https://cauc.bysjy.com.cn/module/news?type_id=13049&menu_id=28132"),
        ("中国民航大学就业公众号（微信搜索）", wx("中国民航大学 就业")),
        ("云南大学云就业平台", "https://jobs.ynu.edu.cn/index"),
        ("大理大学就业平台", "https://dldx.jysd.com/"),
        ("昆明理工大学就业网", "http://job.kmust.edu.cn/"),
        ("提醒", "院系辅导员/班级群通知：竞争范围最小、企业资质经学校审核，务必同步关注"),
    ]),
    ("🏛️ 一、国家级官方平台（权威性最高）", [
        ("国家大学生就业服务平台 24365（岗位）", "https://job.ncss.cn/student/jobs/index.html"),
        ("24365 主站", "https://www.ncss.cn"),
        ("24365 微信公众号 ncssfwh（微信搜索）", wx("ncssfwh 国家大学生就业服务平台")),
        ("国聘网（国资委+教育部+人社部）", "https://www.iguopin.com"),
        ("国聘·国资央企招聘专区", "https://cujiuye.iguopin.com"),
        ("国聘·校园招聘频道", "https://xiaoyuan.iguopin.com"),
        ("中国公共招聘网（人社部）", "http://job.mohrss.gov.cn"),
        ("国资委官网·人事专栏（政务公开→人事）", "http://www.sasac.gov.cn"),
        ("国资小新（公众号 guozixiaoxin）", wx("国资小新 央企 校园招聘")),
        ("工信部中小企业百日招聘（中国中小企业服务网）", "https://www.chinasme.cn"),
    ]),
    ("🏫 二、校园专属渠道（竞争压力最小）", [
        ("海投网（16地区150+高校宣讲会）", "https://www.haitou.cc"),
        ("梧桐果（宣讲会/校招）", "https://www.wutongguo.com"),
        ("应届生求职网（宣讲会日历/面经）", "https://www.yingjiesheng.com"),
        ("本校就业信息网（见上方第一板块）", "https://cauc.bysjy.com.cn/"),
        ("目标城市高校就业网（按城市搜）", bd("2027届 校园招聘 就业信息网 昆明")),
        ("高校宣讲会日历（按校名搜）", bd("宣讲会 日程 2027届 昆明")),
    ]),
    ("💼 三、综合类招聘平台（海投初筛）", [
        ("应届生求职网（51job 旗下）", "https://www.yingjiesheng.com"),
        ("智联招聘·校园", "https://xiaoyuan.zhaopin.com"),
        ("前程无忧 51job", "https://www.51job.com"),
        ("BOSS直聘（直聊 HR）", "https://www.zhipin.com"),
        ("实习僧（实习/校招，可转正标签）", "https://www.shixiseng.com"),
        ("猎聘·校园（中大型企业/外企）", "https://campus.liepin.com"),
        ("拉勾网（互联网垂直）", "https://www.lagou.com"),
        ("中华英才网", "https://www.chinahr.com"),
        ("一览英才网（电力/医疗等细分行业）", "https://www.job1001.com"),
    ]),
    ("🎯 四、行业垂直渠道", [
        ("牛客网（技术岗/内推/面经）", "https://www.nowcoder.com"),
        ("腾讯招聘（微信搜索）", wx("腾讯招聘 校园招聘")),
        ("字节跳动校园招聘", "https://jobs.bytedance.com/campus/"),
        ("阿里巴巴招聘（微信搜索）", wx("阿里巴巴 校园招聘")),
        ("京东校园招聘（微信搜索）", wx("京东招聘 校园招聘")),
        ("快手招聘（微信搜索）", wx("快手招聘 校园招聘")),
        ("工商银行招聘", "https://job.icbc.com.cn"),
        ("农业银行招聘", "https://career.abchina.com.cn"),
        ("建设银行招聘", "https://job2.ccb.com"),
        ("中国银行招聘公告", "https://www.boc.cn/aboutboc/bi4/"),
        ("交通银行招聘", "https://job.bankcomm.com"),
        ("邮储银行招聘", "https://www.psbc.com/cn/gyyc/rczp/xyzp/"),
        ("宝洁校园招聘（P&G）", "https://www.pgcareers.com"),
        ("养生堂·农夫山泉校招", "https://jobs.yst.com.cn/campus"),
        ("英特尔中国校招", "https://chinacampus.jobs.intel.cn"),
        ("阿斯利康校招（Moka 平台）", "https://app.mokahr.com/campus-recruitment/astrazeneca"),
        ("ASML 阿斯麦（微信搜索）", wx("ASML 阿斯麦 校园招聘")),
        ("咨询公司（奥纬等，按名搜）", bd("咨询公司 校园招聘 2027 中国")),
        ("国家电网招聘", "https://zhaopin.sgcc.com.cn"),
        ("中石油招聘", "https://zhaopin.cnpc.com.cn"),
        ("中国移动招聘", "https://job.10086.cn/personal/campus/"),
        ("中国联通招聘（搜索）", bd("中国联通 校园招聘 2027")),
        ("中国电信招聘（搜索）", bd("中国电信 校园招聘 2027")),
        ("中国铁路人才网（18 个铁路局唯一官方）", "https://rczp.china-railway.com.cn"),
        ("军队人才网（文职唯一官方）", "http://81rc.81.cn"),
    ]),
    ("🗺️ 五、地方性渠道（回省/下沉就业）", [
        ("云南省人社厅", "https://hrss.yn.gov.cn"),
        ("大理州人民政府（本地公告）", "https://www.dali.gov.cn"),
        ("云南省国资委", "https://gzw.yn.gov.cn"),
        ("山东人社·乐业山东（求职招聘）", "https://hrss.shandong.gov.cn"),
        ("潍坊市人力资源和社会保障局", "https://rsj.weifang.gov.cn"),
        ("北京高校大学生就业创业信息网", "https://www.bjbys.net.cn"),
        ("广东“粤就业”小程序（微信搜索）", wx("粤就业 小程序 高校毕业生")),
        ("四川“川e就”平台（搜索）", bd("川e就 四川大学生就业服务平台")),
        ("河南省毕业生就业信息网（搜索）", bd("河南省毕业生就业信息网")),
        ("浙江省大学生网上就业市场（搜索）", bd("浙江省大学生网上就业市场")),
        ("内蒙古北疆就业网（搜索）", bd("北疆就业网 内蒙古 大学生")),
        ("辽宁省大学生智慧就业创业平台（搜索）", bd("辽宁省大学生智慧就业创业平台")),
        ("当地人社局公众号（微信搜索 潍坊/昆明/大理）", wx("人社局 招聘 事业单位 潍坊 昆明 大理")),
        ("山东国资 / 广东国资（地方国资委公众号）", wx("山东国资 校园招聘 国企")),
    ]),
    ("🤝 六、内推与社交渠道（提高通过率）", [
        ("学长学姐/校友内推（院系校友群、求职社团）", bd("中国民航大学 校友 内推 就业")),
        ("脉脉（学长学姐内推通道）", "https://maimai.cn"),
        ("牛客网·内推帖", "https://www.nowcoder.com"),
        ("OfferShow 内推群（搜索）", bd("OfferShow 内推群 校招")),
        ("知乎“企业名+内推”（搜索）", bd("秋招 内推 央国企 知乎")),
        ("LinkedIn 领英（外企/校友）", "https://www.linkedin.com"),
    ]),
    ("📢 七、社群与信息聚合（信息差加速器）", [
        ("大厂官方校招群（腾讯/字节校园大使）", wx("校园大使 校招群 内推码")),
        ("国企央企校招群（地方国资委公众号）", wx("国资 校招群 内推")),
        ("垂直行业社群（AI/运营等）", wx("AI 求职 社群 内推")),
        ("知乎“求职数据通”", "https://www.zhihu.com"),
        ("校招信息管理平台（offer情报局）", "https://offerqingbaoju.cn"),
        ("2027秋招企业汇总表（givemeoc）", "https://www.givemeoc.com"),
        ("2027届秋招国企汇总（搜索）", bd("2027届 秋招 国企 汇总表")),
    ]),
]

# 需要「自己站内搜」的平台 —— 这里只列**关键词与去哪搜**，不给假链接。
# 原 SEARCH_SITES（site:xxx.com 的百度链接）已按第 2 步重构全部删除。
MANUAL_SEARCH = [
    ("国聘网", "iguopin.com", "校园招聘 → 城市「昆明/大理」→ 单位性质「国有企业」"),
    ("24365", "job.ncss.cn", "找工作 → 地点云南 → 单位性质「国有企业/事业单位」"),
    ("中国公共招聘网", "job.mohrss.gov.cn", "招聘信息 → 地区选云南"),
    ("BOSS直聘", "zhipin.com", "城市切昆明/大理 → 筛「应届生」"),
    ("智联招聘·校园", "xiaoyuan.zhaopin.com", "选云南 → 按「国企/上市公司」筛"),
    ("前程无忧", "51job.com", "校园招聘频道 → 城市昆明"),
    ("实习僧", "shixiseng.com", "城市昆明/大理 → 类型「校招」"),
    ("牛客网", "nowcoder.com", "「校招日程」看时间轴；搜「云南」看本地岗位"),
    ("应届生求职网", "yingjiesheng.com", "首页公告列表从上往下刷"),
    ("高校就业信息网", "各校域名", "按校名找就业网 → 「招聘信息」栏"),
    ("政府/人社公告", "*.gov.cn", "人社厅/人社局 → 「通知公告」栏，搜「招聘」"),
]


def _clean_groups() -> None:
    """清掉 CHANNEL_GROUPS 里的伪直达：把搜索引擎链接换成一句「该去搜什么」。

    注意只清**伪直达**（点开是搜索引擎）—— 像 BOSS、智联这种平台入口是真链接，
    要留着（它们本身就是「平台」，不是被冒充成「企业官方页」）。
    """
    from . import linkcheck
    for i, (title, items) in enumerate(CHANNEL_GROUPS):
        new = []
        for name, url in items:
            if url and linkcheck.is_fake_direct(url):
                kw = ""
                if "query=" in url:
                    from urllib.parse import unquote
                    kw = unquote(url.split("query=")[-1])
                elif "wd=" in url:
                    from urllib.parse import unquote
                    kw = unquote(url.split("wd=")[-1]).replace("site:", "")
                tip = f"（不给假链接：自己在站内搜「{kw}」）" if kw else "（不给假链接：自己在站内搜）"
                new.append((name.replace("（搜索）", "").replace("（微信搜索）", "") + tip, ""))
            else:
                new.append((name, url))
        CHANNEL_GROUPS[i] = (title, new)


_clean_groups()


def manual_search_notes(city: str = "", keyword: str = "", year: str = "2027届") -> list:
    """站内搜索说明：[("平台", "去哪搜", "该敲的词")] —— **故意不给链接**。

    没有站内搜索直达的平台，与其编一条「看着像搜索页」的链接，不如把
    「去哪个栏目、敲什么词」讲明白 —— 这比假直达有用。
    """
    kw = " / ".join([k for k in [keyword, city, "应届生"] if k]) or "你的专业词 + 昆明 / 大理"
    out = []
    for name, site, where in MANUAL_SEARCH:
        out.append((name, site, f"{where}；关键词敲「{kw}」，换几个词多搜几次"))
    return out


def official_entries() -> list:
    """所有**真能点开**的入口（官方站 + 平台站）：[(名称, 链接, 板块)]。"""
    from . import linkcheck
    out = []
    for title, items in CHANNEL_GROUPS:
        for name, url in items:
            if url and not linkcheck.is_fake_direct(url):
                out.append((name, url, title))
    return out


def fake_direct_left() -> list:
    """自检用：还有没有残留的伪直达（应该恒为空列表）。"""
    from . import linkcheck
    bad = []
    for title, items in CHANNEL_GROUPS:
        for name, url in items:
            if url and linkcheck.is_fake_direct(url):
                bad.append((name, url))
    return bad


def search_links(city: str = "", keyword: str = "", year: str = "2027届") -> list:
    """【已按第 2 步重构移除】原来生成的是一堆百度 `site:` 伪直达。

    现在只返回**官方入口**（点开真的是官方网站），搜索动作交给
    `manual_search_notes()` 用文字说清楚。保留函数名是为了让老代码不至于直接崩，
    但返回里不会再有搜索引擎链接。
    """
    return [(name, url) for name, url, _ in official_entries()]
