# -*- coding: utf-8 -*-
"""投递台账（ledger）—— 防「投了不知道投过」。

为什么单独一个模块
------------------
《重构指令》第 3 步：投递台账要和网申助手、岗位页打通。
但真正要命的是一条**不可逆的规则**：

    烟草系统 **同一批次只能报 1 个单位 1 个岗位，重复投递直接取消资格**。

所以台账不能只是「记录」，它得能在你**登记的那一刻**就拦住你。
这个模块负责三件事：

  1. `check_new()`  登记前的校验：该不该拦、拦到什么程度（block / warn / ok）
  2. `parse_ledger_text()` / `to_tsv()`  网申助手页面上填完一键复制，
     回 InternHub 粘一下就能入库（油猴脚本碰不到本地数据库，只能走剪贴板）
  3. `tobacco_rows()`  按烟草口径筛出「已经占了名额」的记录

用法：
    from ihub import ledger
    ledger.check_new("云南省烟草专卖局", "信息中心技术岗", existing_rows)
    # → {"level": "block", "msg": "...", "hits": [...]}
"""
from __future__ import annotations

import re

# 烟草口径的主体：省局、州市局、中烟、卷烟厂、复烤、烟叶
TOBACCO_WORDS = ("烟草", "中烟", "专卖局", "烟叶", "卷烟", "复烤", "烟厂")

# 已经在流程里的状态（占了名额）；「未通过」不算占名额（可以改报别的）
ACTIVE_STAGES = ("已投", "笔试", "面试", "Offer")

# 台账列名（TSV 表头）—— 网申助手复制出来的就是这一行
COLS = ["公司", "岗位", "城市", "状态", "投递日期", "链接", "备注"]

# 表头别名（网申助手 / 手写 / 从别处粘贴都可能不同）
_ALIAS = {
    "company": ("公司", "公司名称", "单位", "单位名称", "企业", "company"),
    "title": ("岗位", "职位", "职位名称", "岗位名称", "title", "job"),
    "city": ("城市", "工作城市", "地点", "工作地点", "city"),
    "stage": ("状态", "进度", "投递状态", "stage"),
    "applied_at": ("投递日期", "投递时间", "日期", "applied_at"),
    "url": ("链接", "网址", "网申链接", "url", "link"),
    "note": ("备注", "note", "说明"),
}


def is_tobacco(company: str) -> bool:
    """是不是烟草系统的主体（省局/中烟/卷烟厂/复烤…）。"""
    c = str(company or "")
    return any(w in c for w in TOBACCO_WORDS)


def _n(s) -> str:
    """归一化：去空白、去括号注释，方便比对。"""
    return re.sub(r"[\s（(].*?[)）]?$", "", str(s or "").strip())


def same_unit(a: str, b: str) -> bool:
    """两个公司名是不是同一家（互相包含即算，去掉括号注释后比）。"""
    x, y = _n(a), _n(b)
    if not x or not y:
        return False
    return x == y or x in y or y in x


def same_job(a: str, b: str) -> bool:
    x, y = _n(a), _n(b)
    if not x or not y:
        return False
    return x == y or x in y or y in x


def tobacco_rows(rows) -> list:
    """已有记录里「占了烟草名额」的那些（状态在 ACTIVE_STAGES 里）。"""
    out = []
    for r in rows or []:
        if is_tobacco(r.get("company")):
            if str(r.get("stage") or "") in ACTIVE_STAGES or str(r.get("stage") or "").startswith("未"):
                out.append(r)
    return out


def check_new(company: str, title: str, existing, stage: str = "未投") -> dict:
    """登记一条新记录之前问一句：这能登吗？

    返回 {"level": "block"|"warn"|"ok", "msg": str, "hits": [记录]}

    - **block**：烟草口径下，同一批次只能 1 单位 1 岗 —— 已经有别的烟草记录占着名额了，
      再登就是重复投递，会被**取消资格**。网页端必须用红色强警告 + 二次确认。
    - **warn**：非烟草单位，同名公司 + 同一岗位已经登过。
    - **ok**：没冲突。
    """
    hits_tobacco = [r for r in tobacco_rows(existing)
                    if not str(r.get("stage") or "").startswith("未通过")]
    if is_tobacco(company):
        # 1) 同一单位同一岗位，登第二次
        for r in hits_tobacco:
            if same_unit(r.get("company"), company) and same_job(r.get("title"), title):
                return {
                    "level": "block",
                    "msg": f"烟草系统「{r.get('company')}｜{r.get('title')}」已经登记过"
                           f"（进度：{r.get('stage')}）—— 重复报名会被**取消资格**，别再登了。",
                    "hits": [r],
                }
        # 2) 同一批次只能 1 个单位 1 个岗位
        if hits_tobacco:
            r = hits_tobacco[0]
            return {
                "level": "block",
                "msg": f"⚠️ 烟草铁律：**同一批次只能报 1 个单位 1 个岗位**。"
                       f"你已经登记了「{r.get('company')}｜{r.get('title')}」（进度：{r.get('stage')}）—— "
                       f"再报「{company}」属于重复投递，**会直接取消资格**。"
                       f"除非前一条已确认放弃（把它的进度改成「未通过」），否则不要登记第二条。",
                "hits": [r],
            }
        return {"level": "ok", "msg": "", "hits": []}

    for r in (existing or []):
        if same_unit(r.get("company"), company) and same_job(r.get("title"), title):
            return {
                "level": "warn",
                "msg": f"「{r.get('company')}｜{r.get('title')}」已经在台账里"
                       f"（进度：{r.get('stage')}）—— 确认是不同批次/不同岗位再登记。",
                "hits": [r],
            }
    return {"level": "ok", "msg": "", "hits": []}


# ─────────────────────── 网申助手 → 台账（走剪贴板） ───────────────────────

def to_tsv(records) -> str:
    """把记录导成 TSV（带表头），网申助手复制出来的就是这个格式。"""
    lines = ["\t".join(COLS)]
    for r in records or []:
        lines.append("\t".join(str(r.get(k) or "").replace("\t", " ") for k in
                               ("company", "title", "city", "stage", "applied_at", "url", "note")))
    return "\n".join(lines)


def _pick(header_row, row, key, idx_fallback):
    """在表头里找这一列；找不到就用位置兜底。"""
    for i, h in enumerate(header_row):
        h = str(h or "").strip().lower()
        if h and h in [a.lower() for a in _ALIAS[key]]:
            return str(row[i] if i < len(row) else "").strip()
    if 0 <= idx_fallback < len(row):
        return str(row[idx_fallback]).strip()
    return ""


def parse_ledger_text(text: str) -> list:
    """解析粘贴进来的台账（TSV / CSV / 一行一条都行）。

    兼容三种情况：
      ① 网申助手复制的（有表头，Tab 分隔）
      ② 从 Excel / 飞书另存的 CSV（逗号分隔，可能带引号）
      ③ 手打的一行一条（"公司 岗位 城市 状态"用空格或 | 隔开）
    返回 [{"company","title","city","stage","applied_at","url","note"}]。
    """
    out = []
    raw = [ln for ln in str(text or "").splitlines() if ln.strip()]
    if not raw:
        return out

    sep = "\t" if "\t" in raw[0] else ("," if "," in raw[0] else None)

    # CSV 必须用真解析器 —— 岗位名里带逗号（"设备运维,设备"）会被裸 split 切坏
    rows: list = []
    if sep == ",":
        import csv as _csv
        import io as _io
        rows = [list(r) for r in _csv.reader(_io.StringIO("\n".join(raw)))]
    elif sep == "\t":
        rows = [line.split("\t") for line in raw]
    else:
        rows = [re.split(r"[|]{1}| {2,}", line) for line in raw]

    header = None
    if sep and rows:
        cells = [c.strip() for c in rows[0]]
        low = [c.lower() for c in cells]
        if any(a.lower() in low for key in _ALIAS for a in _ALIAS[key]):
            header = cells

    for i, row in enumerate(rows):
        if header is not None and i == 0:
            continue
        row = [str(c).strip() for c in row]
        if not row or not any(row):
            continue
        if header is not None:
            rec = {k: _pick(header, row, k, j) for j, k in enumerate(
                ("company", "title", "city", "stage", "applied_at", "url", "note"))}
        else:
            rec = {}
            for j, k in enumerate(("company", "title", "city", "stage", "applied_at", "url", "note")):
                rec[k] = row[j] if j < len(row) else ""
        # 状态认不出来就当「已投」—— 网申助手里点「记录本次投递」的场景就是已投
        if rec.get("stage") not in ("未投", "已投", "笔试", "面试", "Offer", "未通过"):
            rec["stage"] = "已投" if rec.get("company") else "未投"
        if not rec.get("company"):
            continue
        out.append(rec)
    return out


def merge_plan(parsed, existing) -> dict:
    """把解析出来的记录分成 新增 / 只改状态 / 冲突 三堆，交给网页端展示。"""
    plan = {"new": [], "update": [], "conflict": []}
    for rec in parsed:
        chk = check_new(rec["company"], rec.get("title", ""), existing)
        if chk["level"] == "block":
            plan["conflict"].append((rec, chk))
            continue
        hit = None
        for r in existing or []:
            if same_unit(r.get("company"), rec["company"]) and same_job(r.get("title"), rec.get("title", "")):
                hit = r
                break
        if hit:
            plan["update"].append((rec, hit))
        else:
            plan["new"].append(rec)
    return plan


def summary_line(plan) -> str:
    return (f"新增 {len(plan['new'])} 条 ｜ 更新状态 {len(plan['update'])} 条 ｜ "
            f"冲突拦截 {len(plan['conflict'])} 条")
