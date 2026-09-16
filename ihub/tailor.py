# -*- coding: utf-8 -*-
"""按岗位方向生成定向简历与网申文案（罗广睿 · 2027 届）。

设计：内容全部放在 data/resume_kit.json（可手改，改完网页与脚本一起生效），
本模块只负责「识别方向 → 选料 → 排版」，不编造任何内容。

对外主要接口：
    detect(jd, title)              -> (方向key, 各方向得分, 是否没线索)
    analyze(jd, key)               -> {score, hit, miss, ...}
    resume_docx(key, path, ctx)    -> 生成 docx（与 pdf 版同款排版）
    build_pdf(key, path, ctx)      -> 生成 pdf（需 reportlab）
    md_resume / html_resume        -> 文本与网页版
    fill_pack(key, ctx)            -> [(字段名, 文案)]，网申表单直接用
    packs() / base_fields()        -> 给网申助手脚本用的资料包
"""
from __future__ import annotations

import json
import os
import re

from . import config

KIT_PATH = os.path.join(config.PROJECT_ROOT, "data", "resume_kit.json")

ORDER = ["hw", "iot", "ai", "auto", "test", "aviation", "prod", "media"]

# 方向识别词表（越靠前的关键词权重越高；命中越多越可能被选中）
DIRKEYS = {
    "hw": ["嵌入式", "单片机", "mcu", "stm32", "freertos", "rtos", "固件", "驱动", "bsp", "硬件",
           "电子工程", "pcb", "电路", "射频", "传感器", "c语言", "c/c++", "arm", "i2c", "spi",
           "uart", "can", "电气工程", "器件", "datasheet"],
    "iot": ["物联网", "iot", "mqtt", "智能硬件", "传感网", "华为云", "设备接入", "nb-iot", "lora",
            "zigbee", "coap", "边缘计算", "智能家居", "智慧", "网关"],
    "ai": ["人工智能", "大模型", "llm", "算法", "langchain", "rag", "智能体", "agent", "prompt",
           "提示词", "nlp", "机器学习", "深度学习", "aigc", "模型", "向量", "chatgpt", "知识库"],
    "auto": ["自动化", "控制", "机器人", "ros", "运动控制", "plc", "伺服", "产线", "调试",
             "系统集成", "导航", "slam", "运动规划", "机电", "设备工程", "电气"],
    "test": ["测试", "qa", "质量管理", "运维", "技术支持", "售后", "实施", "it支持", "系统维护",
             "网络管理", "故障", "排障", "客服工程", "驻场"],
    "aviation": ["民航", "航空", "机场", "空管", "航司", "运输", "国企", "事业单位", "烟草",
                 "电力", "铁路", "政府", "集团", "航道", "通航"],
    "prod": ["产品经理", "解决方案", "售前", "需求分析", "项目经理", "技术支持", "实施顾问",
             "产品设计", "用户研究", "brd", "prd", "商业化"],
    "media": ["运营", "新媒体", "内容", "短视频", "直播", "剪辑", "编导", "文案", "市场", "品牌",
              "营销", "社群", "编辑", "账号", "图文", "增长", "投放"],
}

# JD ↘ 匹配分析用的通用词表
VOCAB = [
    "物联网", "嵌入式", "单片机", "硬件", "电子", "通信", "计算机", "软件", "测试", "数据", "数据库",
    "算法", "人工智能", "大模型", "机器学习", "网络", "运维", "技术支持", "产品", "数据分析",
    "数据采集", "接口", "脚本", "提示词", "需求", "文档", "项目管理", "系统", "自动化", "电气",
    "控制", "云计算", "前端", "后端", "小程序", "安全", "民航", "机场",
    "Python", "C++", "C语言", "Java", "SQL", "Excel", "Linux", "Git", "MQTT", "Docker", "STM32",
    "OpenHarmony", "ROS", "SQLite", "Streamlit", "LangChain",
    "沟通", "协作", "抗压", "责任心", "学习能力", "执行", "逻辑", "细心", "服务意识",
    "运营", "视频", "剪辑", "设计", "市场", "新媒体",
]

_CACHE: dict = {}


def kit(refresh: bool = False) -> dict:
    if refresh or "kit" not in _CACHE:
        with open(KIT_PATH, encoding="utf-8") as f:
            _CACHE["kit"] = json.load(f)
    return _CACHE["kit"]


def direction(key: str) -> dict:
    k = kit()
    if key == "universal":
        return k["universal"]
    return k["directions"][key]


def label_of(key: str) -> str:
    k = kit()
    if key == "universal":
        return k["universal"]["label"]
    return k["directions"][key]["label"]


def file_of(key: str) -> str:
    return direction(key).get("file", "万能通用版")


# ────────────────────────────────────────── 方向识别
def detect(jd: str = "", title: str = "") -> tuple[str, dict, bool]:
    t = (jd or "").lower()
    tt = (title or "").lower()
    scores = {}
    for k in ORDER:
        s = 0
        for w in DIRKEYS[k]:
            n = t.count(w)
            if n:
                s += min(n, 4) * (2 if len(w) > 3 else 1)
            if tt and w in tt:
                s += 6                      # 岗位名里出现，权重高
        scores[k] = s
    best, bv = "ai", -1
    for k in ORDER:
        if scores[k] > bv:
            bv, best = scores[k], k
    return best, scores, bv <= 0


# ────────────────────────────────────────── 匹配分析
def _corpus() -> str:
    k = kit()
    parts = [k["profile"].get("intent", ""), k["profile"].get("gpa", ""),
             k["profile"].get("english", ""), k["profile"].get("major", ""),
             k["profile"].get("college", ""), k["courses"],
             " ".join(k["eduBullets"]), " ".join(k["honors"]),
             " ".join(k["highlights"].values()), " ".join(k["skills"].values()),
             " ".join(x.get("desc", "") for x in k["practice"].values()),
             " ".join(d.get("selfeval", "") for d in k["directions"].values()),
             k["universal"].get("selfeval", "")]
    for p in k["projects"].values():
        parts += [p.get("title", ""), p.get("role", ""), " ".join(p.get("bullets", []))]
    return " ".join(parts).lower()


def analyze(jd: str, key: str) -> dict:
    text = jd or ""
    low = text.lower()
    terms = [v for v in VOCAB if v.lower() in low]
    terms += re.findall(r"[A-Za-z][A-Za-z0-9+#./\-]{1,16}", text)
    seen, lst = set(), []
    for t in terms:
        lk = t.lower()
        if lk not in seen and len(lk) > 1:
            seen.add(lk)
            lst.append(t)
    mine = _corpus()
    hit = [t for t in lst if t.lower() in mine]
    miss = [t for t in lst if t.lower() not in mine]
    dir_hit = [w for w in DIRKEYS.get(key, []) if w in low]
    dir_covered = [w for w in dir_hit if w in mine]
    base = (len(hit) / len(lst)) if lst else 0.5
    bonus = (len(dir_covered) / len(dir_hit)) if dir_hit else base
    score = int(round((base * 0.45 + bonus * 0.55) * 100))
    return {"score": max(35, min(96, score)), "hit": hit, "miss": miss,
            "dirHit": dir_hit, "dirCovered": dir_covered}


# ────────────────────────────────────────── 选料
def _ctx(ctx: dict | None) -> tuple[str, str]:
    ctx = ctx or {}
    return str(ctx.get("company") or "").strip(), str(ctx.get("title") or "").strip()


def _intent(key: str, ctx: dict | None) -> str:
    d = direction(key)
    co, jt = _ctx(ctx)
    if co or jt:
        tgt = " · ".join([x for x in (jt, co) if x])
        return f"应聘 {tgt}　|　{d['intent']}"
    return d["intent"]


def _projects(key: str):
    k = kit()
    d = direction(key)
    out = []
    for pk, idxs in d["projects"].items():
        p = k["projects"][pk]
        bl = p["bullets"] if idxs is None else [p["bullets"][i] for i in idxs]
        out.append((p, bl))
    return out


def _edu_bullets() -> list:
    k = kit()
    p = k["profile"]
    return [f'GPA {p["gpa"]}，无挂科；连续三年获校级“人民奖学金”（2023–2026 学年）',
            f'英语：{p["english"]}，可无障碍阅读英文技术文档与器件 datasheet',
            f'主修课程：{k["courses"]}；操作系统、数据结构与算法、数据库系统原理']


# ────────────────────────────────────────── 输出：Markdown / 网页
def md_resume(key: str, ctx: dict | None = None) -> str:
    k = kit()
    d = direction(key)
    p = k["profile"]
    L = [f'# {p["name"]}',
         "　|　".join([p["gender"], p["political"], p["birth"], p["hometown"]]),
         "　|　".join([p["phone"], p["email"], p["city"]]),
         f'{p["school"]} · {p["college"]} · {p["major"]}（{p["degree"]}在读） · 2027 届',
         f'**求职意向：{_intent(key, ctx)}**', '',
         "## 核心亮点"]
    L += ["- " + k["highlights"][h] for h in d["highlights"]]
    L += ["", "## 教育背景",
          f'**{p["school"]}　{p["college"]}**　2023.09 – 2027.06',
          f'{p["major"]}（{p["degree"]}，工学学士）　专业方向：电子信息与智能系统　2027 届']
    L += ["- " + b for b in _edu_bullets()]
    L += ["", "## 专业技能"] + ["- " + k["skills"][s] for s in d["skill_order"]]
    L += ["", "## 项目经历"]
    for prj, bl in _projects(key):
        L.append(f'**{prj["title"]}｜{prj["role"]}**　{prj["time"]}')
        L += ["- " + b for b in bl]
        L.append("")
    L += ["## 实践与校园经历"] + ["- " + k["practiceLine"][x] for x in d["practice"]]
    L += ["", "## 荣誉与证书"] + ["- " + b for b in k["honors"]]
    L += ["", "## 自我评价", d["selfeval"], "",
          f'作品与代码：{p["github"]}（InternHub 工具源码，可核验）']
    return "\n".join(L)


def plain_resume(key: str, ctx: dict | None = None) -> str:
    md = md_resume(key, ctx)
    md = re.sub(r"^#+\s*", "", md, flags=re.M)
    md = md.replace("**", "")
    return re.sub(r"^-\s", "• ", md, flags=re.M)


def html_resume(key: str, ctx: dict | None = None, for_word: bool = False) -> str:
    k = kit()
    d = direction(key)
    p = k["profile"]
    H = []
    if for_word:
        H.append('<div class="cv-name">' + p["name"] + "</div>")
    else:
        H.append('<div class="cv-name">' + p["name"] + "</div>")
    H.append('<div class="cv-meta">' + "　|　".join([p["gender"], p["political"], p["birth"], p["hometown"]]) + "</div>")
    H.append('<div class="cv-meta">' + "　|　".join([p["phone"], p["email"], p["city"]]) + "</div>")
    H.append('<div class="cv-meta">' + f'{p["school"]} · {p["college"]} · {p["major"]}（{p["degree"]}在读） · 2027 届' + "</div>")
    H.append('<div class="cv-intent">求职意向：<b>' + _intent(key, ctx) + "</b></div>")
    H.append("<h3>核心亮点</h3><ul>" + "".join("<li>" + k["highlights"][x] + "</li>" for x in d["highlights"]) + "</ul>")
    H.append("<h3>教育背景</h3>")
    H.append(f'<div class="h"><span>{p["school"]}　{p["college"]}</span><span>2023.09 – 2027.06</span></div>')
    H.append('<div class="h"><span class="sub">'
             f'{p["major"]}（{p["degree"]}，工学学士）　专业方向：电子信息与智能系统</span><span>2027 届</span></div>')
    H.append("<ul>" + "".join("<li>" + b + "</li>" for b in _edu_bullets()) + "</ul>")
    H.append("<h3>专业技能</h3><ul>" + "".join("<li>" + k["skills"][s] + "</li>" for s in d["skill_order"]) + "</ul>")
    H.append("<h3>项目经历</h3>")
    for prj, bl in _projects(key):
        H.append(f'<div class="h"><span>{prj["title"]}｜{prj["role"]}</span><span>{prj["time"]}</span></div>')
        H.append("<ul>" + "".join("<li>" + b + "</li>" for b in bl) + "</ul>")
    H.append("<h3>实践与校园经历</h3><ul>"
             + "".join("<li>" + k["practiceLine"][x] + "</li>" for x in d["practice"]) + "</ul>")
    H.append("<h3>荣誉与证书</h3><ul>" + "".join("<li>" + b + "</li>" for b in k["honors"]) + "</ul>")
    H.append("<h3>自我评价</h3><p>" + d["selfeval"] + "</p>")
    H.append('<div class="foot">作品与代码：' + p["github"] + "（InternHub 工具源码，可核验）</div>")
    return "\n".join(H)


WORD_CSS = (
    'body{font-family:"微软雅黑";font-size:10.5pt;color:#262626;line-height:1.5}'
    'h3{font-size:12pt;color:#1F4E79;border-bottom:1px solid #afc7de;margin:12pt 0 5pt}'
    '.cv-name{font-size:19pt;font-weight:bold;color:#1F4E79;text-align:center}'
    '.cv-meta{text-align:center;color:#6b6b6b;font-size:9pt;margin-top:2pt}'
    '.cv-intent{text-align:center;margin:6pt 0}'
    'ul{margin:0;padding-left:16pt}li{margin:1pt 0}'
    '.h{display:flex;justify-content:space-between;font-weight:bold;margin-top:5pt}'
    '.h .sub{font-weight:normal;color:#6b6b6b;font-size:9pt}'
    '.foot{text-align:center;color:#94a3b8;font-size:8pt;margin-top:8pt}'
)


def word_html(key: str, ctx: dict | None = None) -> str:
    return ('<html xmlns:o="urn:schemas-microsoft-com:office:office" '
            'xmlns:w="urn:schemas-microsoft-com:office:word"><head><meta charset="utf-8">'
            f'<title>{kit()["profile"]["name"]} 简历</title><style>{WORD_CSS}</style></head><body>'
            + html_resume(key, ctx, for_word=True) + "</body></html>")


# ────────────────────────────────────────── 输出：docx
def resume_docx(key: str, out_path: str, ctx: dict | None = None) -> str:
    """生成一页纸、单栏、ATS 友好的 docx（排版与 pdf 版一致）。"""
    from docx import Document
    from docx.shared import Pt, Cm, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    ACCENT, DARK, GREY, FONT = "1F4E79", "262626", "6B6B6B", "微软雅黑"
    BODY, LEAD, SEC, NAME = 8.8, 1.12, 11.0, 17.5

    k = kit()
    d = direction(key)
    p = k["profile"]

    def sf(run, size=BODY, bold=False, color=DARK):
        run.font.name = FONT
        run.font.size = Pt(size)
        run.bold = bold
        run.font.color.rgb = RGBColor.from_string(color)
        rPr = run._element.get_or_add_rPr()
        rf = rPr.find(qn("w:rFonts"))
        if rf is None:
            rf = OxmlElement("w:rFonts")
            rPr.append(rf)
        for a in ("w:eastAsia", "w:ascii", "w:hAnsi"):
            rf.set(qn(a), FONT)

    doc = Document()
    sec0 = doc.sections[0]
    sec0.page_height, sec0.page_width = Cm(29.7), Cm(21.0)
    sec0.top_margin, sec0.bottom_margin = Cm(1.15), Cm(1.0)
    sec0.left_margin = sec0.right_margin = Cm(1.6)
    st = doc.styles["Normal"]
    st.font.name = FONT
    st.font.size = Pt(BODY)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)

    def para(text="", size=BODY, bold=False, color=DARK, align=None, after=1, line=LEAD):
        pp = doc.add_paragraph()
        pp.paragraph_format.space_after = Pt(after)
        pp.paragraph_format.line_spacing = line
        if align is not None:
            pp.alignment = align
        if text:
            sf(pp.add_run(text), size, bold, color)
        return pp

    def tabbed(left, right, size=BODY, bold=True, color=DARK, before=2.5, after=1):
        pp = doc.add_paragraph()
        pp.paragraph_format.space_before = Pt(before)
        pp.paragraph_format.space_after = Pt(after)
        pp.paragraph_format.line_spacing = LEAD
        pp.paragraph_format.tab_stops.add_tab_stop(Cm(17.6), WD_TAB_ALIGNMENT.RIGHT)
        sf(pp.add_run(left), size, bold, color)
        if right:
            sf(pp.add_run("\t" + right), size - 0.4, False, GREY)
        return pp

    def bullet(text, size=BODY):
        pp = doc.add_paragraph()
        pp.paragraph_format.left_indent = Cm(0.36)
        pp.paragraph_format.first_line_indent = Cm(-0.36)
        pp.paragraph_format.space_after = Pt(1)
        pp.paragraph_format.line_spacing = LEAD
        sf(pp.add_run("• "), size, False, ACCENT)
        sf(pp.add_run(text), size, False, DARK)
        return pp

    def section(title):
        pp = doc.add_paragraph()
        pp.paragraph_format.space_before = Pt(5)
        pp.paragraph_format.space_after = Pt(1.5)
        pp.paragraph_format.line_spacing = 1.0
        sf(pp.add_run(title), SEC, True, ACCENT)
        pPr = pp._p.get_or_add_pPr()
        bdr = OxmlElement("w:pBdr")
        bot = OxmlElement("w:bottom")
        bot.set(qn("w:val"), "single")
        bot.set(qn("w:sz"), "8")
        bot.set(qn("w:space"), "2")
        bot.set(qn("w:color"), "AFC7DE")
        bdr.append(bot)
        pPr.append(bdr)

    para(p["name"], NAME, True, ACCENT, WD_ALIGN_PARAGRAPH.CENTER, after=0.5, line=1.0)
    para("　|　".join([p["gender"], p["political"], p["birth"], p["hometown"]]),
         8.4, False, GREY, WD_ALIGN_PARAGRAPH.CENTER, after=0.5, line=1.0)
    para("　|　".join([p["phone"], p["email"], p["city"]]),
         9.2, False, DARK, WD_ALIGN_PARAGRAPH.CENTER, after=0.5, line=1.0)
    para(f'{p["school"]} · {p["college"]} · {p["major"]}（{p["degree"]}在读） · 2027 届',
         8.8, False, GREY, WD_ALIGN_PARAGRAPH.CENTER, after=1.5, line=1.0)
    pp = doc.add_paragraph()
    pp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pp.paragraph_format.space_after = Pt(1)
    pp.paragraph_format.line_spacing = 1.0
    sf(pp.add_run("求职意向："), 9.4, True, ACCENT)
    sf(pp.add_run(_intent(key, ctx)), 9.4, False, DARK)

    section("核心亮点")
    for h in d["highlights"]:
        bullet(k["highlights"][h])

    section("教育背景")
    tabbed(f'{p["school"]}　{p["college"]}', "2023.09 – 2027.06", size=9.2, before=0)
    tabbed(f'{p["major"]}（{p["degree"]}，工学学士）　专业方向：电子信息与智能系统',
           "2027 届", size=8.6, bold=False, color=GREY, before=0)
    for b in _edu_bullets():
        bullet(b)

    section("专业技能")
    for s in d["skill_order"]:
        bullet(k["skills"][s])

    section("项目经历")
    for prj, bl in _projects(key):
        tabbed(f'{prj["title"]}｜{prj["role"]}', prj["time"], before=3)
        for b in bl:
            bullet(b)

    section("实践与校园经历")
    for x in d["practice"]:
        bullet(k["practiceLine"][x])

    section("荣誉与证书")
    for b in k["honors"]:
        bullet(b)

    section("自我评价")
    para(d["selfeval"], BODY, False, DARK, after=2)
    para(f'作品与代码：{p["github"]}（InternHub 工具源码，可核验）', 8.2, False, GREY, after=0)

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    doc.save(out_path)
    return out_path


# ────────────────────────────────────────── 输出：pdf
_PDF_READY = False


def _pdf_fonts():
    global _PDF_READY
    if _PDF_READY:
        return True
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.pdfmetrics import registerFontFamily
        from reportlab.pdfbase.ttfonts import TTFont
        pdfmetrics.registerFont(TTFont("MSYH", r"C:\Windows\Fonts\msyh.ttc", subfontIndex=0))
        pdfmetrics.registerFont(TTFont("MSYH-B", r"C:\Windows\Fonts\msyhbd.ttc", subfontIndex=0))
        registerFontFamily("MSYH", normal="MSYH", bold="MSYH-B",
                           italic="MSYH", boldItalic="MSYH-B")
        _PDF_READY = True
        return True
    except Exception:
        return False


def build_pdf(key: str, out_path: str, ctx: dict | None = None) -> str:
    """生成单页 PDF；环境缺 reportlab / 中文字体时抛异常，由调用方降级为 docx。"""
    if not _pdf_fonts():
        raise RuntimeError("缺少 reportlab 或中文字体，无法生成 PDF")
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib.colors import HexColor
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle
    from reportlab.platypus.flowables import HRFlowable

    ACCENT, DARK, GREY, RULE = (HexColor("#1F4E79"), HexColor("#262626"),
                                HexColor("#6B6B6B"), HexColor("#AFC7DE"))
    BODY, LEAD, SEC = 8.8, 12.0, 11.0
    k = kit()
    d = direction(key)
    p = k["profile"]

    def esc(s):
        return str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    st_n = ParagraphStyle("n", fontName="MSYH-B", fontSize=17.5, leading=21, textColor=ACCENT,
                          alignment=TA_CENTER, spaceAfter=0.5)
    st_m = ParagraphStyle("m", fontName="MSYH", fontSize=8.4, leading=11, textColor=GREY,
                          alignment=TA_CENTER, spaceAfter=0.5)
    st_c = ParagraphStyle("c", fontName="MSYH", fontSize=9.2, leading=12, textColor=DARK,
                          alignment=TA_CENTER, spaceAfter=0.5)
    st_i = ParagraphStyle("i", fontName="MSYH", fontSize=9.4, leading=12.5, textColor=DARK,
                          alignment=TA_CENTER, spaceAfter=1)
    st_s = ParagraphStyle("s", fontName="MSYH-B", fontSize=SEC, leading=14, textColor=ACCENT,
                          spaceBefore=4, spaceAfter=0.5)
    st_b = ParagraphStyle("b", fontName="MSYH", fontSize=BODY, leading=LEAD, textColor=DARK,
                          leftIndent=9, bulletIndent=0.5, spaceAfter=0.8)
    st_l = ParagraphStyle("l", fontName="MSYH-B", fontSize=BODY + 0.5, leading=LEAD + 1.5, textColor=DARK)
    st_r = ParagraphStyle("r", fontName="MSYH", fontSize=BODY - 0.4, leading=LEAD + 1.5,
                          textColor=GREY, alignment=TA_RIGHT)

    flow = [Paragraph(esc(p["name"]), st_n),
            Paragraph(esc("　|　".join([p["gender"], p["political"], p["birth"], p["hometown"]])), st_m),
            Paragraph(esc("　|　".join([p["phone"], p["email"], p["city"]])), st_c),
            Paragraph(esc(f'{p["school"]} · {p["college"]} · {p["major"]}（{p["degree"]}在读） · 2027 届'), st_m),
            Paragraph(f'求职意向：<font name="MSYH-B">{esc(_intent(key, ctx))}</font>', st_i)]

    def section(t):
        flow.append(Paragraph(esc(t), st_s))
        flow.append(HRFlowable(width="100%", thickness=0.8, color=RULE, spaceBefore=0, spaceAfter=1.5))

    def bullet(t):
        flow.append(Paragraph(esc(t), st_b, bulletText="•"))

    def head(left, right):
        tb = Table([[Paragraph(esc(left), st_l), Paragraph(esc(right), st_r)]],
                   colWidths=[13.7 * cm, 4.1 * cm])
        tb.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                ("TOPPADDING", (0, 0), (-1, -1), 2),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                                ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        flow.append(tb)

    section("核心亮点")
    for h in d["highlights"]:
        bullet(k["highlights"][h])
    section("教育背景")
    head(f'{p["school"]}　{p["college"]}', "2023.09 – 2027.06")
    for b in _edu_bullets():
        bullet(b)
    section("专业技能")
    for s in d["skill_order"]:
        bullet(k["skills"][s])
    section("项目经历")
    for prj, bl in _projects(key):
        head(f'{prj["title"]}｜{prj["role"]}', prj["time"])
        for b in bl:
            bullet(b)
    section("实践与校园经历")
    for x in d["practice"]:
        bullet(k["practiceLine"][x])
    section("荣誉与证书")
    for b in k["honors"]:
        bullet(b)
    section("自我评价")
    flow.append(Paragraph(esc(d["selfeval"]),
                          ParagraphStyle("se", fontName="MSYH", fontSize=BODY, leading=12.6,
                                         textColor=DARK, spaceAfter=1)))
    flow.append(Paragraph(f'<font size="7.6" color="#6B6B6B">作品与代码：{esc(p["github"])}'
                          f'（InternHub 工具源码，可核验）</font>', st_m))

    doc = SimpleDocTemplate(out_path, pagesize=A4, topMargin=1.1 * cm, bottomMargin=0.9 * cm,
                            leftMargin=1.6 * cm, rightMargin=1.6 * cm,
                            title=f'{p["name"]}-简历', author=p["name"])
    doc.build(flow)
    return out_path


# ────────────────────────────────────────── 网申文案
def fill_pack(key: str, ctx: dict | None = None) -> list:
    """返回 [(字段名, 文案)]，覆盖网申表单常见栏目。"""
    k = kit()
    d = direction(key)
    p = k["profile"]
    co, jt = _ctx(ctx)
    hl = [k["highlights"][x] for x in d["highlights"]]
    exp = []
    for prj, bl in _projects(key):
        exp.append(f'【{prj["title"]}】{prj["role"]}　{prj["time"]}\n' + "\n".join("- " + b for b in bl))
    if co or jt:
        reason = (f'您好！我是{k["profile"]["school"]}{p["college"]}{p["major"]}专业 2027 届学生{p["name"]}，'
                  f'看到{("贵单位（" + co + "）") if co else "贵司"}{("正在招聘「" + jt + "」") if jt else "的招聘信息"}，'
                  f'非常感兴趣并希望投递。我的匹配点：{hl[0]}；{hl[1]}。'
                  f'学习能力强、动手经验多、做事踏实，可保证稳定实习与工作时间，期待与您进一步沟通！')
    else:
        reason = (f'您好！我是{k["profile"]["school"]}{p["college"]}{p["major"]}专业 2027 届学生{p["name"]}。'
                  f'我的匹配点：{hl[0]}；{hl[1]}。学习能力强、动手经验多，期待进一步沟通！')
    short_intro = (f'{p["school"]}{p["college"]}{p["major"]} 2027 届本科生，GPA 3.47/4.0 无挂科，'
                   f'连续三年校级人民奖学金，CET-4 与 CET-6（446 分）均已通过。{hl[0]}。{hl[1]}。')
    return [
        ("姓名", p["name"]),
        ("性别 / 民族 / 政治面貌", f'{p["gender"]} / {p["nation"]} / {p["political"]}'),
        ("出生日期", p["birth"]),
        ("手机 / 邮箱", f'{p["phone"]} / {p["email"]}'),
        ("现居地 / 籍贯", f'{p["city"]} / {p["hometown"]}'),
        ("学校名称", p["school"]),
        ("学院 / 系别", p["college"]),
        ("专业名称", p["major"]),
        ("学历 / 学位", f'{p["degree"]}（工学学士，在读）'),
        ("入学 / 毕业时间", "2023.09 / 2027.06"),
        ("GPA", p["gpa"]),
        ("外语水平", p["english"]),
        ("求职意向", _intent(key, ctx)),
        ("项目经历（可整段粘贴）", "\n\n".join(exp)),
        ("技能特长", "\n".join(k["skills"][s] for s in d["skill_order"])),
        ("获奖情况", "\n".join(k["honors"])),
        ("实践经历", "\n\n".join(
            f'【{k["practice"][x]["company"]}】{k["practice"][x]["title"]}　{k["practice"][x]["time"]}\n'
            f'{k["practice"][x]["desc"]}' for x in d["practice"])),
        ("自我评价（按此方向定制）", d["selfeval"]),
        ("自我介绍（短版）", short_intro),
        ("申请理由 / 求职信", reason),
    ]


def quickcard(key: str | None = None) -> str:
    """整份速填卡（txt）：基础字段 + 各方向技能/自我评价/申请理由。"""
    k = kit()
    p = k["profile"]
    L = ["罗广睿 · 网申速填卡（技术与内容岗通用）", "=" * 72,
         "说明：标【】的需要本人核对/补充；其余可直接粘贴到网申表单。", "",
         "一、基本信息",
         f'姓名：{p["name"]}　　性别：{p["gender"]}　　民族：{p["nation"]}',
         f'出生日期：{p["birth"]}　　政治面貌：{p["political"]}　　婚姻状况：未婚',
         f'手机：{p["phone"]}　　邮箱：{p["email"]}',
         f'现居地：{p["city"]}　　籍贯/生源地：{p["hometown"]}',
         "身份证号：【填】　　微信号：【填】　　QQ：【填】", "",
         "二、教育信息",
         f'学校名称：{p["school"]}', f'学院/院系：{p["college"]}',
         f'专业名称：{p["major"]}　　专业类别：电子信息类 / 计算机类（物联网工程）',
         "学历：本科　　学位：工学学士（在读）　　培养方式：全日制",
         "入学时间：2023.09　　毕业时间：2027.06　　届别：2027 届",
         f'GPA：{p["gpa"]}（无挂科）　　专业排名：【如学院有排名可填】',
         f'外语水平：{p["english"]}',
         f'主修课程：{k["courses"]}、操作系统、数据结构与算法、数据库系统原理',
         "作品/代码：https://github.com/chuYI00/internhub", "",
         "三、求职意向",
         "意向岗位：AI 应用开发 / 嵌入式开发 / 物联网开发 / 自动化（按实际岗位名称填写）",
         "意向城市：【按岗位填：大理 / 昆明 / 潍坊 / 北京 / 上海 / 不限】",
         "期望薪资：面议　　到岗时间：可按要求时间到岗　　实习时长：可连续 2 个月以上", "",
         "四、项目经历（可整段粘贴）"]
    for pk, prj in k["projects"].items():
        L.append(f'【{prj["title"]}】{prj["role"]}　{prj["time"]}')
        L += ["  - " + b for b in prj["bullets"]]
        L.append("")
    L.append("五、实践与校园经历（可整段粘贴）")
    for pk, pr in k["practice"].items():
        L += [f'【{pr["company"]}】{pr["title"]}　{pr["time"]}', "  " + pr["desc"], ""]
    L.append("六、荣誉与证书")
    L += ["  - " + h for h in k["honors"]]
    L += ["  - 校园跑团干事（2023.09 – 至今）", "", "七、技能特长（按岗位方向选一组粘贴）"]
    for key2 in ORDER:
        d = k["directions"][key2]
        L.append(f'—— 投【{d["label"]}】用这组 ——')
        L += ["  " + k["skills"][s] for s in d["skill_order"]]
        L.append("")
    L.append("八、自我评价（按岗位方向选一段粘贴）")
    L += ["【万能通用版】", k["universal"]["selfeval"], ""]
    for key2 in ORDER:
        d = k["directions"][key2]
        L += [f'【投 {d["label"]}】', d["selfeval"], ""]
    L.append("九、申请理由 / 求职信（按方向选一段）")
    for key2 in ["universal"] + ORDER:
        L += [f'—— {label_of(key2)} ——', fill_pack(key2, None)[-1][1], ""]
    L += ["=" * 72,
          "配套材料（同目录 简历材料/）：",
          "  · 万能通用简历：02_万能通用版_罗广睿_中国民航大学.pdf / .docx",
          "  · 岗位定向简历：岗位定向简历/ 目录下按方向各一份",
          "  · 定制工具：05_投递工作台.html（粘贴 JD 自动生成定向简历与文案）",
          "  · 自动填表：网申助手.user.js（油猴）/ 网申书签.txt（免装扩展）"]
    return "\n".join(L)


# ────────────────────────────────────────── 给网申助手脚本用的资料包
BASE_FIELDS = {
    "name": "", "gender": "", "birth": "", "political": "", "nation": "", "idcard": "",
    "phone": "", "email": "", "wechat": "", "qq": "",
    "school": "", "college": "", "major": "", "degree": "", "edu_range": "2023.09-2027.06",
    "enroll": "2023.09", "graduate_year": "2027.06", "gpa": "", "rank": "",
    "city": "", "hometown": "", "address": "", "postal": "",
    "english": "", "certificates": "", "scholarship": "",
    "intent": "", "expected_city": "", "expected_salary": "面议", "available": "可按要求时间到岗",
    "self_eval": "", "highlights": "", "skills": "", "experiences": "", "reason": "",
    "emergency_name": "", "emergency_phone": "", "emergency_relation": "", "marital": "未婚",
}

SCRIPT_KEYS = list(BASE_FIELDS.keys())


def base_fields() -> dict:
    k = kit()
    p = k["profile"]
    out = dict(BASE_FIELDS)
    out.update({
        "name": p["name"], "gender": p["gender"], "birth": p["birth"],
        "political": p["political"], "nation": p["nation"],
        "phone": p["phone"], "email": p["email"],
        "school": p["school"], "college": p["college"], "major": p["major"],
        "degree": p["degree"], "gpa": p["gpa"], "city": p["city"], "hometown": p["hometown"],
        "english": "CET-4、CET-6（446 分），可阅读英文技术文档",
        "certificates": "大学英语四级（CET-4）、大学英语六级（CET-6）",
        "scholarship": "连续三年获校级“人民奖学金”（2023—2026 学年）",
        "intent": k["universal"]["intent"],
        "self_eval": k["universal"]["selfeval"],
        "highlights": "\n".join(k["highlights"][x] for x in k["universal"]["highlights"]),
        "skills": "\n".join(k["skills"][s] for s in k["universal"]["skill_order"]),
        "experiences": "\n".join(
            f'{v["title"]}|{v["role"]}|{v["time"]}|{v["bullets"][0]}' for v in k["projects"].values()),
    })
    return out


def packs() -> dict:
    k = kit()
    out = {"universal": {"label": "万能通用版（技术岗通用）",
                         "intent": k["universal"]["intent"],
                         "self_eval": k["universal"]["selfeval"],
                         "highlights": "\n".join(k["highlights"][x] for x in k["universal"]["highlights"]),
                         "skills": "\n".join(k["skills"][s] for s in k["universal"]["skill_order"]),
                         "reason": fill_pack("universal", None)[-1][1]}}
    for key in ORDER:
        d = k["directions"][key]
        out[key] = {"label": "岗位方向：" + d["label"],
                    "intent": d["intent"], "self_eval": d["selfeval"],
                    "highlights": "\n".join(k["highlights"][x] for x in d["highlights"]),
                    "skills": "\n".join(k["skills"][s] for s in d["skill_order"]),
                    "reason": fill_pack(key, None)[-1][1]}
    return out
