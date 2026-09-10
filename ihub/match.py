# -*- coding: utf-8 -*-
"""岗位打分：钱多 / 轻松 / 与专业契合 → 0-100 匹配分 + 推荐理由。

说明：这是**启发式打分**（依据岗位标题、标签、薪资等公开字段），
不代表真实工作强度或发展前景，仅用于帮你快速筛出"看起来更适合"的岗位。
"""
from . import prefs as prefs_mod


def _salary_score(job, p) -> float:
    lo = job.get("salary_min")
    hi = job.get("salary_max")
    try:
        lo = int(lo) if lo is not None else None
        hi = int(hi) if hi is not None else None
    except (TypeError, ValueError):
        lo = hi = None
    val = hi if hi else lo
    if not val:
        return 0.50, "薪资未标注"
    if val >= 250:
        s, tag = 1.00, "高薪"
    elif val >= 200:
        s, tag = 0.90, "薪资较高"
    elif val >= 150:
        s, tag = 0.75, "薪资中上"
    elif val >= 120:
        s, tag = 0.60, "薪资中等"
    elif val >= p.get("min_salary", 100):
        s, tag = 0.45, "薪资偏低"
    else:
        s, tag = 0.20, "低于期望薪资"
    return s, tag


def _match_score(job, p):
    kws = p.get("major_keywords") or []
    blob = " ".join(str(job.get(k) or "") for k in ("title", "tags", "industry", "company")).lower()
    hits = [k for k in kws if k.lower() in blob]
    s = min(1.0, len(hits) / 3.0)
    return s, (f"契合关键词：{'、'.join(hits[:4])}" if hits else "专业契合度一般")


def _easy_score(job, p):
    tags = str(job.get("tags") or "")
    title = str(job.get("title") or "")
    blob = (tags + " " + title)
    easy_hits = [t for t in (p.get("easy_tags") or []) if t in blob]
    hard_hits = [t for t in (p.get("hard_keywords") or []) if t in blob]
    s = 0.65 + 0.12 * len(easy_hits) - 0.20 * len(hard_hits)
    s = max(0.0, min(1.0, s))
    if hard_hits:
        note = f"强度信号：{'、'.join(hard_hits[:3])}"
    elif easy_hits:
        note = f"轻松信号：{'、'.join(easy_hits[:3])}"
    else:
        note = "强度无明显信号"
    return s, note


def score_job(job, p=None) -> dict:
    p = p or prefs_mod.load()
    ws = float(p.get("w_salary", 0.4))
    wm = float(p.get("w_match", 0.35))
    we = float(p.get("w_easy", 0.25))
    total_w = ws + wm + we or 1.0
    ws, wm, we = ws / total_w, wm / total_w, we / total_w

    s_sal, n_sal = _salary_score(job, p)
    s_mat, n_mat = _match_score(job, p)
    s_easy, n_easy = _easy_score(job, p)
    score = round(100 * (ws * s_sal + wm * s_mat + we * s_easy))
    return {
        "score": score,
        "s_salary": round(s_sal * 100),
        "s_match": round(s_mat * 100),
        "s_easy": round(s_easy * 100),
        "reason": "；".join([n_sal, n_mat, n_easy]),
    }


def rank(rows, p=None, top=None):
    p = p or prefs_mod.load()
    out = []
    for r in rows:
        sc = score_job(r, p)
        merged = dict(r)
        merged.update(sc)
        out.append(merged)
    out.sort(key=lambda x: x["score"], reverse=True)
    return out[:top] if top else out
