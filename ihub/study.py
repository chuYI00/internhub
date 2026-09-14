# -*- coding: utf-8 -*-
"""备考方案数据（用户自选目标岗位 → 对应备考方案）+ 本地打卡进度。"""
import json
import os

from . import config

CHECK_PATH = os.path.join(config.DATA_DIR, "study_checklist.json")

TIME_PLAN = [
    ("基础期（第1-4周）", "系统学行测各模块 + 专业知识框架；每天 2-3 小时，周末做一套摸底卷"),
    ("强化期（第5-9周）", "分模块刷题 + 错题本；每周 2 套整卷计时；专业知识背重点"),
    ("冲刺期（第10-12周）", "套卷模考 + 时政/行业动态 + 面试提前准备；复盘错题而非刷新题"),
    ("考前1周", "只看错题本与高频考点；调整作息；备齐证件与网申材料"),
]

COMMON_PRACTICE = [
    ("粉笔（题库+模考）", "https://fenbi.com"),
    ("华图在线（题库/直播课）", "https://www.huatu.com"),
    ("中公题库/资料", "https://www.offcn.com"),
]

COMMON_OFFICIAL = [
    ("国家大学生就业服务平台（24365）", "https://www.ncss.cn"),
    ("国聘网（国资委/教育部/人社部）", "https://www.iguopin.com"),
    ("中国公共招聘网（人社部）", "http://job.mohrss.gov.cn"),
    ("云南省人力资源和社会保障厅", "https://hrss.yn.gov.cn"),
]

INTERVIEW = [
    "结构化面试：自我介绍（1 分钟/3 分钟两版）、求职动机、岗位匹配、情景应变",
    "行业认知：目标行业/公司近一年新闻、业务、社会责任——面试官最爱问“为什么来我们这”",
    "用 STAR 法准备 5 个故事（InternHub 项目、抖音账号、LangChain 问答、OpenHarmony、政府实践）",
    "常见追问：为什么不去机场？为什么跨专业？能接受倒班/异地吗？",
]

TARGETS = {
    "中国烟草（云南中烟 / 省局）": {
        "note": "云南烟草系统岗位多、待遇好；笔试通常考行测+公共基础+烟草行业知识，部分岗位加专业科目",
        "subjects": ["行政职业能力测验（言语/数量/判断/资料分析）", "公共基础知识（政治/法律/经济/科技/时政）",
                     "烟草行业知识（烟草专卖法、行业概况与政策）", "专业知识（按岗位：计算机/电气/机械/财务/营销等）",
                     "写作/申论（部分岗位）"],
        "courses": [("粉笔·行测系统班（付费，性价比高）", "https://fenbi.com"),
                    ("华图·烟草招聘专项课", "https://www.huatu.com"),
                    ("中公·烟草招聘考试用书/课程", "https://www.offcn.com"),
                    ("B站免费课：烟草招聘笔试", "https://search.bilibili.com/all?keyword=%E7%83%9F%E8%8D%89%E6%8B%9B%E8%81%98%20%E7%AC%94%E8%AF%95%20%E8%A1%8C%E6%B5%8B"),
                    ("中国大学MOOC（补专业基础）", "https://www.icourse163.org")],
        "practice": [("粉笔题库+模考（行测主力）", "https://fenbi.com"),
                     ("华图在线题库", "https://www.huatu.com"),
                     ("中公题库", "https://www.offcn.com"),
                     ("烟草笔试真题（百度直达）", "https://www.baidu.com/s?wd=%E4%B8%AD%E5%9B%BD%E7%83%9F%E8%8D%89%20%E6%8B%9B%E8%81%98%20%E7%AC%94%E8%AF%95%20%E7%9C%9F%E9%A2%98%20%E4%BA%91%E5%8D%97")],
        "official": [("国家烟草专卖局（政策/公告）", "https://www.tobacco.gov.cn"),
                     ("云南中烟招聘公告（搜索直达）", "https://www.baidu.com/s?wd=%E4%BA%91%E5%8D%97%E4%B8%AD%E7%83%9F%20%E6%8B%9B%E8%81%98%20%E5%85%AC%E5%91%8A"),
                     ("云南省烟草专卖局招聘（搜索直达）", "https://www.baidu.com/s?wd=%E4%BA%91%E5%8D%97%E7%9C%81%E7%83%9F%E8%8D%89%E4%B8%93%E5%8D%96%E5%B1%80%20%E6%8B%9B%E8%81%98"),
                     ("学习强国（时政积累）", "https://www.xuexi.cn")],
    },
    "公务员（国考 / 云南省考）": {
        "note": "行测+申论；云南定向选调与省考岗位多，注意应届生身份与专业目录",
        "subjects": ["行政职业能力测验", "申论（归纳概括/综合分析/应用文/大作文）",
                     "面试（结构化/无领导）", "部分岗位专业科目"],
        "courses": [("粉笔·国考系统班", "https://fenbi.com"),
                    ("华图·公务员笔试课程", "https://www.huatu.com"),
                    ("中公·公务员课程", "https://www.offcn.com"),
                    ("B站免费课：申论系统课", "https://search.bilibili.com/all?keyword=%E7%94%B3%E8%AE%BA%20%E7%B3%BB%E7%BB%9F%E8%AF%BE"),
                    ("学习强国（时政/金句）", "https://www.xuexi.cn")],
        "practice": [("粉笔模考（每周）", "https://fenbi.com"),
                     ("历年国考/省考真题（百度直达）", "https://www.baidu.com/s?wd=%E5%9B%BD%E8%80%83%20%E8%A1%8C%E6%B5%8B%20%E7%9C%9F%E9%A2%98%20%E4%B8%8B%E8%BD%BD"),
                     ("华图在线题库", "https://www.huatu.com")],
        "official": [("国家公务员局", "http://www.scs.gov.cn"),
                     ("云南省人社厅（省考公告）", "https://hrss.yn.gov.cn")],
    },
    "事业单位 / 选调 / 三支一扶": {
        "note": "职测+综合应用能力+公共基础；地方公告集中发布，注意户籍与专业限制",
        "subjects": ["职业能力倾向测验", "综合应用能力（A/B/C/D/E 类）", "公共基础知识", "部分地区考申论/写作"],
        "courses": [("粉笔·事业单位课程", "https://fenbi.com"),
                    ("华图·事业单位", "https://www.huatu.com"),
                    ("B站免费课：职测 综应", "https://search.bilibili.com/all?keyword=%E4%BA%8B%E4%B8%9A%E5%8D%95%E4%BD%8D%20%E8%81%8C%E6%B5%8B%20%E7%BB%BC%E5%BA%94")],
        "practice": [("粉笔题库（职测）", "https://fenbi.com"),
                     ("事业单位真题（百度直达）", "https://www.baidu.com/s?wd=%E4%BA%8B%E4%B8%9A%E5%8D%95%E4%BD%8D%20%E8%81%8C%E6%B5%8B%20%E7%9C%9F%E9%A2%98%20%E4%BA%91%E5%8D%97")],
        "official": [("大理州人民政府（本地公告）", "https://www.dali.gov.cn"),
                     ("云南省人社厅", "https://hrss.yn.gov.cn")],
    },
    "银行秋招（云南各分行）": {
        "note": "EPI 行测+英语+综合知识+性格测评；网申越早越好，重视实习与证书",
        "subjects": ["EPI（行测类）", "英语（托业式）", "综合知识（经济金融/会计/计算机/时政）",
                     "性格测评", "半结构化面试 + 无领导"],
        "courses": [("粉笔·银行招聘课程", "https://fenbi.com"),
                    ("华图·银行秋招课程", "https://www.huatu.com"),
                    ("B站免费课：银行 EPI", "https://search.bilibili.com/all?keyword=%E9%93%B6%E8%A1%8C%20%E7%A7%8B%E6%8B%9B%20EPI%20%E7%B3%BB%E7%BB%9F%E8%AF%BE")],
        "practice": [("银行笔试题库（百度直达）", "https://www.baidu.com/s?wd=%E9%93%B6%E8%A1%8C%20%E7%A7%8B%E6%8B%9B%20%E7%AC%94%E8%AF%95%20%E7%9C%9F%E9%A2%98%20%E9%A2%98%E5%BA%93"),
                     ("粉笔题库", "https://fenbi.com")],
        "official": [("中国银行招聘公告", "https://www.boc.cn/aboutboc/bi4/"),
                     ("工商银行招聘", "https://job.icbc.com.cn"),
                     ("农业银行招聘", "https://career.abchina.com.cn"),
                     ("建设银行招聘", "https://job2.ccb.com"),
                     ("交通银行招聘", "https://job.bankcomm.com"),
                     ("邮储银行招聘", "https://www.psbc.com/cn/gyyc/rczp/xyzp/"),
                     ("云南银行秋招汇总页", "http://m.yinhangzhaopin.com/tag/yunnan_509_1.html")],
    },
    "央国企（国聘 / 24365 渠道）": {
        "note": "公告零散、批次多；建议把网申截止时间统一记到本工具「📮 网申跟踪」",
        "subjects": ["行政能力测试（多数）", "专业知识（岗位相关）", "英语/时政（部分）", "结构化面试"],
        "courses": [("粉笔·国企笔面试", "https://fenbi.com"),
                    ("B站免费课：国企笔试", "https://search.bilibili.com/all?keyword=%E5%9B%BD%E4%BC%81%20%E7%AC%94%E8%AF%95%20%E8%A1%8C%E6%B5%8B%20%E7%B3%BB%E7%BB%9F%E8%AF%BE")],
        "practice": [("国企笔试真题（百度直达）", "https://www.baidu.com/s?wd=%E5%9B%BD%E4%BC%81%20%E7%AC%94%E8%AF%95%20%E7%9C%9F%E9%A2%98%20%E8%A1%8C%E6%B5%8B")],
        "official": [("国聘·央国企专区", "https://cujiuye.iguopin.com"),
                     ("国家大学生就业服务平台（央企专区）", "https://job.ncss.cn"),
                     ("中国铁路人才网", "https://rczp.china-railway.com.cn")],
    },
    "军队文职": {
        "note": "公告唯一官方平台：军队人才网；公共科目+专业科目，应届生岗位多",
        "subjects": ["公共科目（政治+岗位能力）", "专业科目（按岗位）", "面试（结构化+专业问答）+ 体检政审"],
        "courses": [("B站免费课：军队文职公共科目", "https://search.bilibili.com/all?keyword=%E5%86%9B%E9%98%9F%E6%96%87%E8%81%8C%20%E5%85%AC%E5%85%B1%E7%A7%91%E7%9B%AE%20%E7%B3%BB%E7%BB%9F%E8%AF%BE"),
                    ("华图·军队文职课程", "https://www.huatu.com")],
        "practice": [("军队文职真题（百度直达）", "https://www.baidu.com/s?wd=%E5%86%9B%E9%98%9F%E6%96%87%E8%81%8C%20%E7%9C%9F%E9%A2%98%20%E5%85%AC%E5%85%B1%E7%A7%91%E7%9B%AE")],
        "official": [("军队人才网（唯一官方）", "http://81rc.81.cn")],
    },
}

CHECK_ITEMS = [
    "今天完成 1 套模块练习并整理错题",
    "背记行业/时政要点 20 分钟",
    "刷 1 组专业题（按岗位方向）",
    "关注 3 个官方渠道的新公告",
    "每周做 1 次整卷计时模考",
    "整理 1 个 STAR 面试故事",
]


def load_checks() -> dict:
    try:
        if os.path.exists(CHECK_PATH):
            with open(CHECK_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def save_checks(data: dict) -> str:
    os.makedirs(os.path.dirname(CHECK_PATH), exist_ok=True)
    with open(CHECK_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return CHECK_PATH
