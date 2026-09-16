# -*- coding: utf-8 -*-
"""把 Markdown 转成可打印的 Word 文档（中文排版友好）。

用法:
    python md2docx.py 输入.md [输出.docx]

支持: # / ## / ### 标题、表格、- 无序列表(含缩进)、1. 有序列表(保留原编号)、
> 引用、--- 分隔线、**加粗**、`行内代码`、*斜体*。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

BODY_FONT = "微软雅黑"
CODE_FONT = "Consolas"
ACCENT = RGBColor(0x1F, 0x3B, 0x73)
GRAY = RGBColor(0x59, 0x59, 0x59)


def set_run_font(run, name: str = BODY_FONT, size: float | None = None) -> None:
    run.font.name = name
    run._element.rPr.rFonts.set(qn("w:eastAsia"), name)
    if size:
        run.font.size = Pt(size)


def add_bottom_border(paragraph) -> None:
    p_pr = paragraph._p.get_or_add_pPr()
    borders = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "6")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), "BFBFBF")
    borders.append(bottom)
    p_pr.append(borders)


def shade_cell(cell, hex_color: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:fill"), hex_color)
    tc_pr.append(shd)


TOKEN_RE = re.compile(r"(\*\*.+?\*\*|`[^`]+`)")


def write_inline(paragraph, text: str, size: float = 10.5, base_bold: bool = False,
                 color: RGBColor | None = None, italic: bool = False) -> None:
    """写入一行文本，处理 **加粗** 与 `行内代码`。"""
    text = text.replace("\\|", "|")
    for part in TOKEN_RE.split(text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            run = paragraph.add_run(part[2:-2])
            set_run_font(run, BODY_FONT, size)
            run.bold = True
        elif part.startswith("`") and part.endswith("`") and len(part) > 2:
            run = paragraph.add_run(part[1:-1])
            set_run_font(run, CODE_FONT, size - 0.5)
            run.font.color.rgb = RGBColor(0xC0, 0x39, 0x2B)
        else:
            run = paragraph.add_run(part)
            set_run_font(run, BODY_FONT, size)
        if base_bold:
            run.bold = True
        if color is not None:
            run.font.color.rgb = color
        if italic:
            run.italic = True


def is_table_sep(line: str) -> bool:
    core = line.strip().strip("|")
    if not core:
        return False
    return all(re.fullmatch(r":?-{2,}:?", c.strip()) for c in core.split("|") if c.strip())


def split_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def build(md_path: Path, docx_path: Path) -> None:
    lines = md_path.read_text(encoding="utf-8").splitlines()
    doc = Document()

    # 页面：A4，页边距 2cm
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
    sec.top_margin = sec.bottom_margin = Cm(1.9)
    sec.left_margin = sec.right_margin = Cm(1.9)

    normal = doc.styles["Normal"]
    normal.font.name = BODY_FONT
    normal.font.size = Pt(10.5)
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), BODY_FONT)
    normal.paragraph_format.space_after = Pt(4)
    normal.paragraph_format.line_spacing = 1.28

    i = 0
    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip()
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        # 表格
        if stripped.startswith("|") and i + 1 < len(lines) and is_table_sep(lines[i + 1]):
            header = split_row(lines[i])
            rows: list[list[str]] = []
            j = i + 2
            while j < len(lines) and lines[j].strip().startswith("|"):
                rows.append(split_row(lines[j]))
                j += 1
            table = doc.add_table(rows=1, cols=len(header))
            table.style = "Table Grid"
            table.alignment = WD_TABLE_ALIGNMENT.CENTER
            for c, text in enumerate(header):
                cell = table.rows[0].cells[c]
                cell.text = ""
                shade_cell(cell, "DCE6F1")
                write_inline(cell.paragraphs[0], text, size=10, base_bold=True, color=ACCENT)
            for row in rows:
                cells = table.add_row().cells
                for c in range(len(header)):
                    value = row[c] if c < len(row) else ""
                    cells[c].text = ""
                    write_inline(cells[c].paragraphs[0], value, size=10)
            doc.add_paragraph()
            i = j
            continue

        # 分隔线
        if re.fullmatch(r"-{3,}|\*{3,}", stripped):
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(6)
            add_bottom_border(p)
            i += 1
            continue

        # 标题
        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            level, text = len(m.group(1)), m.group(2).strip()
            p = doc.add_paragraph()
            pf = p.paragraph_format
            if level == 1:
                pf.space_before, pf.space_after = Pt(12), Pt(6)
                write_inline(p, text, size=15, base_bold=True, color=ACCENT)
                add_bottom_border(p)
            elif level == 2:
                pf.space_before, pf.space_after = Pt(9), Pt(4)
                write_inline(p, text, size=12.5, base_bold=True, color=ACCENT)
            else:
                pf.space_before, pf.space_after = Pt(7), Pt(3)
                write_inline(p, text, size=11, base_bold=True)
            i += 1
            continue

        # 引用
        if stripped.startswith(">"):
            text = stripped.lstrip(">").strip()
            if text:
                p = doc.add_paragraph()
                pf = p.paragraph_format
                pf.left_indent = Cm(0.5)
                pf.space_after = Pt(3)
                write_inline(p, text, size=10, italic=True, color=GRAY)
            i += 1
            continue

        # 列表：无序
        m = re.match(r"^(\s*)[-*+]\s+(.*)$", line)
        if m:
            indent, text = len(m.group(1)), m.group(2)
            p = doc.add_paragraph()
            pf = p.paragraph_format
            pf.left_indent = Cm(0.6 + 0.55 * (indent // 2))
            pf.first_line_indent = Cm(-0.45)
            write_inline(p, ("•　" if indent < 2 else "◦　") + text)
            i += 1
            continue

        # 列表：有序（保留原编号，避免 Word 自动重排）
        m = re.match(r"^(\s*)(\d+)[.、)]\s+(.*)$", line)
        if m:
            indent, num, text = len(m.group(1)), m.group(2), m.group(3)
            p = doc.add_paragraph()
            pf = p.paragraph_format
            pf.left_indent = Cm(0.6 + 0.55 * (indent // 3))
            pf.first_line_indent = Cm(-0.6)
            write_inline(p, f"{num}. {text}")
            i += 1
            continue

        # 结尾斜体说明
        if stripped.startswith("*") and stripped.endswith("*") and not stripped.startswith("**"):
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            write_inline(p, stripped.strip("*"), size=9, italic=True, color=GRAY)
            i += 1
            continue

        # 普通段落
        p = doc.add_paragraph()
        write_inline(p, stripped)
        i += 1

    docx_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(docx_path))
    print(f"OK -> {docx_path}")


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else src.with_suffix(".docx")
    if not src.exists():
        print(f"找不到文件: {src}")
        return 1
    build(src, dst)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
