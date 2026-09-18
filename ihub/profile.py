# -*- coding: utf-8 -*-
"""个人资料（用于生成投递理由与定制简历）。

- 默认值是内置示例，任何使用者都可以在网页「👤 我的资料」里
  上传自己的简历 / 修改字段后保存 → 覆盖 data/profile.json。
- 资料只保存在本机项目 data/ 目录（已在 .gitignore 中排除），不上传任何服务器。
- 注意：这里的 DEFAULT 是**示例占位**，请勿把你的真实手机号/邮箱写进来——
  本仓库是公开的，真实资料请只放在 data/profile.json（已 gitignore），网页「👤 我的资料」里改。
"""
import json
import os

from . import config

PROFILE_PATH = os.path.join(config.DATA_DIR, "profile.json")

DEFAULT = {
    # ⚠️ 铁律：这里**不允许**出现任何真实个人信息，也**不允许**出现看起来像真的手机号/邮箱。
    # 历史上这里放过 "13800000000" 的"示例号码"，结果被直接填进网申表单，
    # 导致投递出去的简历联系方式是错的。教训：宁可留空让字段被跳过，也不能给假号码。
    # 真实资料一律写在 data/profile.json（已 gitignore），或在网页「👤 我的资料」里填。
    "name": "",
    "gender": "男",
    "city": "云南大理",
    "phone": "",
    "email": "",
    "school": "中国民航大学",
    "major": "物联网工程",
    "degree": "本科",
    "edu_range": "2023.09-2027.06",
    "graduate_year": "2027",
    "gpa": "3.47/4.0",
    "scholarship": "连续三年获“人民奖学金”",
    "english": "CET-4、CET-6 已通过，能阅读英文技术文档",
    "intent": "AI 工具应用 / 内容创作 / 软件开发（实习）",
    # 以下为多行文本，一行一条
    "highlights": "\n".join([
        "AI 工具重度使用者：ChatGPT / Gemini / DeepSeek / Claude Code，熟练 Stable Diffusion、UVR 等 AIGC 工具",
        "独立运营抖音主播切片账号，粉丝 3000+，掌握选题-剪辑-发布-复盘全流程",
        "独立开发并开源 InternHub 实习聚合与投递辅助工具（爬虫 + SQLite + Streamlit）",
        "物联网本科 GPA 3.47、连续三年人民奖学金；政府实践与家教经历锻炼细致与表达",
    ]),
    "skills": "\n".join([
        "AI / AIGC：ChatGPT、Gemini、DeepSeek、Claude Code；Stable Diffusion；UVR；提示词工程与 LangChain 应用开发",
        "编程与工具：Python、C；Linux（Ubuntu/WSL2）、Git；SQLite、Streamlit",
        "新媒体：抖音账号运营、短视频剪辑、字幕封面制作",
        "语言证书：CET-4、CET-6；Office / WPS 熟练",
    ]),
    # 一行一条：标题|时间|描述
    "experiences": "\n".join([
        "InternHub 实习岗位聚合与投递辅助工具（独立开发·开源）|2026.09-至今|合规爬虫+SQLite 去重+Streamlit 网页（地区/省份筛选、截止时间、收藏、投递箱），实现按岗位方向自动生成投递理由与定制简历，已在 GitHub 开源",
        "抖音主播切片账号（独立运营）|持续运营|围绕直播内容二次创作，独立完成选题、剪辑、字幕封面与发布，账号粉丝 3000+，用 AI 工具提升内容产出效率",
        "大模型本地知识库问答系统（个人项目）|2026.03-2026.05|Python + LangChain + Chroma + Streamlit 搭建文档问答 Web 应用，集成大模型 API，独立完成部署与测试",
        "政府办公室助理（社会实践）|2025.07-2025.08|文件整理归档与数据录入 100+ 份，群众接待与问题记录反馈 20+ 件，熟悉规范化流程",
        "家教（初中数学/物理）|2024.09-2025.01|一对一制定计划并跟踪效果，学生期末数学 70→85 分",
    ]),
    "certificates": "大学英语四级（CET-4）、六级（CET-6）",
    "self_eval": ("能用 AI 把想法变成真实产品，也懂内容和表达：独立运营过 3000+ 粉丝账号、独立开发并开源过工具、"
                  "做过大模型应用与物联网项目；踏实肯干、学习快，可稳定保证 2 个月以上全职实习。"),
    # ===== 网申自动填表补充字段（留空就是"自动跳过"，填了就能一键填进各家网申系统）=====
    # 这些字段国内网申系统几乎必问，但不影响生成简历，所以单独放一组
    "birth": "",            # 出生日期，如 2005-03
    "political": "",        # 政治面貌，如 共青团员 / 中共党员
    "nation": "",           # 民族，如 汉族
    "idcard": "",           # 身份证号（敏感，建议只在本机填；不填则不填表）
    "wechat": "",           # 微信号
    "qq": "",               # QQ 号
    "college": "",          # 学院，如 计算机科学与技术学院
    "enroll": "2023.09",    # 入学时间
    "rank": "",             # 专业排名，如 8/60
    "hometown": "",         # 籍贯/生源地，如 云南大理
    "address": "",          # 通讯地址
    "postal": "",           # 邮编
    "expected_city": "",    # 期望工作城市，如 昆明、大理
    "expected_salary": "",  # 期望薪资，如 150-200元/天
    "available": "",        # 到岗时间，如 一周内到岗，可实习 6 个月
    "emergency_name": "",   # 紧急联系人姓名
    "emergency_phone": "",  # 紧急联系人电话
    "emergency_relation": "",  # 与本人关系，如 父亲
    "marital": "",          # 婚姻状况（应届一般"未婚"）
}


def load() -> dict:
    data = dict(DEFAULT)
    try:
        if os.path.exists(PROFILE_PATH):
            with open(PROFILE_PATH, "r", encoding="utf-8") as f:
                user = json.load(f)
            for k, v in user.items():
                if v not in (None, ""):
                    data[k] = v
    except Exception:
        pass
    return data


def save(profile: dict) -> str:
    os.makedirs(os.path.dirname(PROFILE_PATH), exist_ok=True)
    with open(PROFILE_PATH, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)
    return PROFILE_PATH


def lines(text: str):
    return [ln.strip() for ln in (text or "").splitlines() if ln.strip()]


def parse_experience(line: str):
    parts = [p.strip() for p in line.split("|")]
    while len(parts) < 3:
        parts.append("")
    return parts[0], parts[1], parts[2]


def extract_from_text(text: str) -> dict:
    """从上传的简历文本里粗略抽取姓名/电话/邮箱/学校，用于预填。"""
    import re
    out = {}
    m = re.search(r"1[3-9]\d{9}", text)
    if m:
        out["phone"] = m.group(0)
    m = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text)
    if m:
        out["email"] = m.group(0)
    for school in ("中国民航大学", "大学", "学院"):
        m = re.search(r"([\u4e00-\u9fa5]{2,12}%s)" % school, text)
        if m:
            out["school"] = m.group(1)
            break
    m = re.search(r"姓\s*名[:：]?\s*([\u4e00-\u9fa5]{2,4})", text)
    if m:
        out["name"] = m.group(1)
    return out
