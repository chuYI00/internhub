# -*- coding: utf-8 -*-
"""按岗位定制简历与投递材料的生成器（本地离线，用真实信息拼装，不做虚假承诺）。

用法：
  from ihub import resume
  resume.build_docx(job, 'out/job_resume.docx')   # 生成定制简历
  resume.apply_message(job)                          # 生成投递开场白/理由
"""
import os

# ---------------- 个人真实信息基线（与你的简历一致，勿夸大） ----------------
NAME = "罗广睿"
PROFILE = {
    "phone": "13500135000",
    "email": "2810845176@qq.com",
    "city": "云南大理",
    "gender": "男",
    "birth": "2005.01.14",
    "politics": "共青团员",
    "school": "中国民航大学",
    "major": "物联网工程",
    "degree": "本科",
    "edu_range": "2023.09-2027.06",
    "gpa": "3.47/4.0",
    "scholarship": "连续三年获“人民奖学金”",
    "english": "CET-4、CET-6 已通过，能阅读英文技术文档",
}

COMMON_SKILLS = [
    "Python / C 基础编程，Linux（Ubuntu / WSL2）、Git 基本操作，Office / WPS 熟练",
    "AI 工具重度用户：ChatGPT / Gemini / DeepSeek / Claude Code",
    "AIGC 创作：Stable Diffusion 文生图、Ultimate Vocal Remover 人声分离",
]

EXPERIENCES = [
    ("抖音主播切片账号 · 独立运营", "2025 年（持续）",
     "围绕主播直播内容二次创作，独立完成选题、剪辑节奏、字幕封面与发布运营，账号粉丝 3000+，对热点与数据反馈敏感，习惯用 AI 工具提效。"),
    ("大模型本地知识库问答系统（个人项目）", "2026.03-2026.05",
     "Python + LangChain + Chroma + Streamlit 搭建文档问答 Web 应用，集成大模型 API，独立完成部署与测试，理解提示词工程与 AI 应用落地。"),
    ("政府办公室助理（社会实践）", "2025.07-2025.08",
     "云南省大理州巍山县大仓镇人民政府：文件整理归档与数据录入 100+ 份、群众接待与问题记录反馈 20+ 件，细心负责、流程规范。"),
    ("OpenHarmony IoT 开发实践", "2025.10-2026.02",
     "独立完成环境搭建、编译烧录与华为云平台设备接入，输出规范化操作文档。"),
    ("家教（初中数学/物理）", "2024.09-2025.01",
     "一对一制定计划并跟踪效果，学生期末数学 70→85 分，表达与共情沟通能力强。"),
]

# ---------------- 方向识别 ----------------
DIR_MEDIA = ["新媒体", "内容", "运营", "直播", "剪辑", "编辑", "文案", "编导", "市场",
             "传播", "短视频", "图文", "电商内容", "AIGC内容", "策划", "品牌", "营销"]
DIR_PM = ["产品经理", "产品", "PM", "需求", "项目", "商业化"]
DIR_AI = ["AI", "人工智能", "大模型", "智能体", "算法", "LangChain", "语音助手", "声学算法"]
DIR_HW = ["硬件", "嵌入式", "电子", "单片机", "MCU", "射频", "声学", "穿戴", "耳机", "音箱",
          "音频", "IoT", "物联网", "测试", "质量", "结构", "驱动", "固件", "软件开发", "开发"]
DIR_SOFT = ["开发", "后端", "前端", "软件", "数据", "算法工程", "运维", "IT", "测试开发"]


def detect_direction(job) -> str:
    blob = " ".join(str(job.get(k) or "") for k in
                    ("title", "company", "tags", "industry", "requirement")).lower()
    if any(k in blob for k in DIR_MEDIA):
        return "media"
    if any(k in blob for k in DIR_AI):
        return "ai"
    if any(k in blob for k in DIR_PM):
        return "pm"
    if any(k in blob for k in DIR_HW):
        return "hw"
    if any(k in blob for k in DIR_SOFT):
        return "soft"
    return "general"


INTENT = {
    "media": "新媒体 / 短视频内容运营 · AI 内容创作（AIGC）方向",
    "ai": "AI 应用 / 大模型产品方向（实习）",
    "pm": "产品经理（AI / 内容 / 硬件方向）实习",
    "hw": "嵌入式 / 物联网 / 硬件研发测试方向（实习）",
    "soft": "软件开发 / 测试 / IT 方向（实习）",
    "general": "运营 / AI 应用 / 工程技术方向（实习，接受培养与轮岗）",
}

DIR_BULLETS = {
    "media": [
        "独立运营抖音主播切片账号，粉丝 3000+：选题-剪辑-字幕封面-发布复盘全流程实操",
        "熟练使用剪映等剪辑工具与 Stable Diffusion、UVR 等 AIGC 工具，能用 AI 把内容产出提效",
        "重度使用 ChatGPT/Gemini/DeepSeek/Claude Code，擅长把工具迁移到真实工作流",
    ],
    "ai": [
        "独立完成基于 LangChain 的大模型知识库问答应用（文档上传→检索→问答），理解提示词与评估",
        "重度使用并研究多款大模型/AIGC 工具（GPT/Gemini/DeepSeek/Claude Code、SD、UVR），能拆解体验并快速落地",
        "既是内容创作者（抖音 3000+ 粉）也是技术学生，能定义场景、理解用户反馈闭环",
    ],
    "pm": [
        "有真实“从 0 到 1”项目复盘：大模型问答应用与抖音账号（3000+ 粉），能拆需求、看数据、迭代",
        "AI 重度用户 + 物联网工程背景，能平衡用户需求、技术实现与成本",
        "文档习惯好、沟通直接（政府实践 100+ 份材料、OpenHarmony 全流程文档）",
    ],
    "hw": [
        "物联网工程本科：嵌入式原理、单片机、计算机网络等系统课程 + GPA 3.47",
        "动手做过完整软硬件项目（ROS2 智能小车、OpenHarmony+Hi3861 开发与华为云接入）",
        "会用 C/Python、Linux/WSL2、Git，能读英文 datasheet，动手调试能力强",
    ],
    "soft": [
        "Python / C 开发调试经验，能做脚本自动化与简单 Web 应用（Streamlit 问答系统）",
        "熟悉 Linux（Ubuntu/WSL2）、Git、工具链（OpenHarmony 编译烧录全流程）",
        "逻辑清晰、文档规范，政府实践与项目经历养成了细心负责的习惯",
    ],
    "general": [
        "学习能力与执行力强：独立完成抖音账号、AI 应用、IoT 项目等多个 0→1 实践",
        "AI 工具重度用户，能快速上手新工具并帮助团队提效",
        "细心负责、沟通好，GPA 3.47、连续三年人民奖学金",
    ],
}


def direction_of(job):
    return detect_direction(job)


def intent_line(job) -> str:
    d = detect_direction(job)
    t = str(job.get("title") or "该岗位").strip()
    c = str(job.get("company") or "").strip()
    city = str(job.get("city") or "").strip()
    target = f"{t}（{c}{('/' + city) if city and city != '全国' else ''}）"
    return f"应聘 {target}　|　{INTENT[d]}"


def apply_message(job) -> str:
    """生成简短、得体、可改写的投递开场白。"""
    d = detect_direction(job)
    t = str(job.get("title") or "该岗位").strip()
    c = str(job.get("company") or "贵司").strip()
    extra = DIR_BULLETS[d][0]
    return (f"您好！我是中国民航大学物联网工程专业 2027 届本科生罗广睿，看到贵司正在招聘「{t}」，"
            f"非常感兴趣并希望投递。我的匹配点：{extra}。同时我是 AI 工具重度用户并做过抖音账号运营"
            f"（粉丝 3000+）等真实项目，学习快、执行强，能稳定实习 2 个月以上。简历详见附件，期待与您进一步沟通！")


def _simplify_path_safe(name: str) -> str:
    import re
    return re.sub(r'[\\/:*?"<>|\s]+', "_", name or "job")[:50]


def build_docx(job, out_path: str) -> str:
    """生成按岗位定制的简历 docx，返回文件路径。"""
    from docx import Document
    from docx.shared import Pt, Cm, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    d = detect_direction(job)
    doc = Document()
    sec = doc.sections[0]
    sec.top_margin = sec.bottom_margin = Cm(1.2)
    sec.left_margin = sec.right_margin = Cm(1.4)

    style = doc.styles["Normal"]
    style.font.name = "微软雅黑"
    style.font.size = Pt(10.5)
    style._element.rPr.rFonts.set(__import__("docx").oxml.ns.qn("w:eastAsia"), "微软雅黑")

    def para(txt="", bold=False, size=10.5, color=None, align=None, space_after=4, space_before=0):
        p = doc.add_paragraph()
        if align:
            p.alignment = align
        p.paragraph_format.space_after = Pt(space_after)
        p.paragraph_format.space_before = Pt(space_before)
        r = p.add_run(txt)
        r.bold = bold
        r.font.size = Pt(size)
        if color:
            r.font.color.rgb = RGBColor.from_string(color)
        return p

    def heading(txt):
        p = para(txt, bold=True, size=13, color="015187", space_before=8, space_after=3)
        pPr = p._p.get_or_add_pPr()
        from docx.oxml.ns import qn
        from docx.oxml import OxmlElement
        pbdr = OxmlElement("w:pBdr")
        bottom = OxmlElement("w:bottom")
        bottom.set(qn("w:val"), "single"); bottom.set(qn("w:sz"), "6")
        bottom.set(qn("w:color"), "015187"); bottom.set(qn("w:space"), "2")
        pbdr.append(bottom); pPr.append(pbdr)

    def bullets(items):
        for it in items:
            p = doc.add_paragraph(style=None)
            p.paragraph_format.left_indent = Cm(0.45)
            p.paragraph_format.space_after = Pt(2)
            r = p.add_run("▪ "); r.font.color.rgb = RGBColor.from_string("015187"); r.font.size = Pt(10)
            r2 = p.add_run(it); r2.font.size = Pt(10.5)

    def kv(label, text):
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(2)
        r = p.add_run(label); r.bold = True; r.font.size = Pt(10.5)
        r2 = p.add_run(text); r2.font.size = Pt(10.5)

    P = PROFILE
    # 头部
    para(NAME, bold=True, size=22, color="015187", align=WD_ALIGN_PARAGRAPH.CENTER, space_after=2)
    para(f"{P['phone']}　|　{P['email']}　|　{P['city']}　|　{P['gender']}　|　{P['politics']}",
         size=9, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=1)
    para(f"{P['school']} · {P['major']}（{P['degree']}在读）　|　毕业：{P['edu_range'].split('-')[1]}",
         size=9, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=6)
    para(intent_line(job), bold=True, size=11, color="015187", space_after=8)

    # 教育
    heading("教育背景")
    kv("中国民航大学　", f"{P['major']}（{P['degree']}）　{P['edu_range']}")
    kv("GPA：", f"{P['gpa']}，无挂科记录；{P['scholarship']}")
    kv("主修课程：", "物联网原理、嵌入式系统、计算机网络、C 语言程序设计、单片机原理、数据库基础")
    kv("英语：", P["english"])

    # 与岗位匹配的亮点（方向相关）
    heading("岗位匹配亮点")
    bullets(DIR_BULLETS[d])

    # 实践经历
    heading("实践经历")
    for title, rng, desc in EXPERIENCES:
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(1)
        r = p.add_run(f"▎{title}　{rng}"); r.bold = True; r.font.size = Pt(10.5)
        kv_desc = doc.add_paragraph()
        kv_desc.paragraph_format.left_indent = Cm(0.45)
        kv_desc.paragraph_format.space_after = Pt(3)
        rr = kv_desc.add_run(desc); rr.font.size = Pt(10)

    # 技能
    heading("技能与工具")
    bullets(COMMON_SKILLS + [
        "短视频剪辑与账号运营（抖音 3000+ 粉），办公软件熟练",
        f"{P['english']}",
    ])

    # 荣誉
    heading("荣誉与校园")
    bullets([P["scholarship"], "大学英语四级（CET-4）、六级（CET-6）",
             "校园跑团干事（2023.09 至今）：活动策划组织、成员联络执行"])

    para("", space_after=0)
    para("（本简历由 InternHub 按岗位方向自动整理，请投递前人工核对后再发送）",
         size=8, color="9AA5B1", align=WD_ALIGN_PARAGRAPH.CENTER)

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    doc.save(out_path)
    return out_path
