# -*- coding: utf-8 -*-
"""任务二（v3）：岗位列表的排序 / 筛选 / 发布时间兜底 / 临期标红。

跑的是**临时数据库副本**，不会动你的真实 data/jobs.db。

运行： venv\\Scripts\\python.exe tests\\test_joblist.py
"""
from __future__ import annotations

import datetime
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PASS = 0
FAIL = 0


def check(name: str, cond: bool, extra=None) -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK] {name}")
    else:
        FAIL += 1
        print(f"  [XX] {name}" + (f"  -> {extra}" if extra is not None else ""))


def main() -> int:
    tmpdir = tempfile.mkdtemp(prefix="ihub_joblist_")
    tmp_db = os.path.join(tmpdir, "jobs.db")
    from ihub import config
    config.DB_PATH = tmp_db                       # 干净库，不碰真实数据
    from ihub import db

    db.init_db()
    today = datetime.date.today()
    d = lambda n: (today + datetime.timedelta(days=n)).isoformat()   # noqa: E731

    # 造数据：发布时间新旧混着、截止日期有近有远有无、城市分散
    seed = [
        dict(source="t", job_id="a1", title="嵌入式工程师", company="云南中烟工业有限责任公司",
             city="昆明", published_at=d(-30), deadline=d(2)),     # 临期 2 天
        dict(source="t", job_id="a2", title="信息化岗", company="云南省烟草专卖局",
             city="大理", published_at=d(-1), deadline=d(30)),
        dict(source="t", job_id="a3", title="运维工程师", company="云南电网有限责任公司",
             city="昆明", published_at=d(-10), deadline=d(1)),     # 临期 1 天
        dict(source="t", job_id="a4", title="设备技术员", company="中国航空工业集团公司",
             city="曲靖", published_at=d(-60), deadline=""),       # 没有截止日期
        dict(source="t", job_id="a5", title="固件开发", company="北京某某科技有限公司",
             city="北京", published_at="", deadline=d(-5)),        # 没发布日期 + 已截止
        dict(source="t", job_id="a6", title="电气工程师", company="安徽某某股份有限公司",
             city="大理", published_at=d(-3), deadline=d(9)),
    ]
    print("[1] 入库：发布时间不许为空")
    res = db.upsert_jobs(seed)
    check("6 条全部入库", res["inserted"] == 6, res)
    rows = db.query(active_only=False)
    blanks = [r for r in rows if not str(r.get("published_at") or "").strip()]
    check("没有 published_at 为空的记录", not blanks, [r["job_id"] for r in blanks])
    a5 = [r for r in rows if r["job_id"] == "a5"][0]
    check("来源没给发布日期的 → 用抓取日兜底", str(a5["published_at"])[:10] == today.isoformat(),
          a5["published_at"])
    check("兜底的会标记为 published_src='fetched'", a5["published_src"] == "fetched",
          a5["published_src"])
    a1 = [r for r in rows if r["job_id"] == "a1"][0]
    check("来源给了发布日期的 → 原样保留并标 'source'",
          a1["published_at"] == d(-30) and a1["published_src"] == "source",
          (a1["published_at"], a1["published_src"]))

    print("[2] fill_published_at：历史上留下的空值也能补齐")
    conn = db.connect()
    conn.execute("UPDATE jobs SET published_at='', published_src='' WHERE job_id='a1'")
    conn.commit(); conn.close()
    n = db.fill_published_at()
    a1b = [r for r in db.query(active_only=False) if r["job_id"] == "a1"][0]
    check("补了 1 条", n == 1, n)
    check("补完不再是空", bool(str(a1b["published_at"]).strip()), a1b["published_at"])
    check("补的是抓取日（不是今天）", str(a1b["published_at"])[:10] != d(-30),
          a1b["published_at"])
    # 上面把 a1 的发布日期改成了抓取日，这里还原，免得污染后面的排序断言
    conn = db.connect()
    conn.execute("UPDATE jobs SET published_at=?, published_src='source' WHERE job_id='a1'",
                 (d(-30),))
    conn.commit(); conn.close()

    print("[3] 排序：发布时间（新→旧）")
    ids = [r["job_id"] for r in db.query(active_only=False, sort="发布时间（新→旧）")]
    check("最新的排最前（a5 = 今天抓取）", ids[0] == "a5", ids)
    check("第二是昨天的 a2", ids[1] == "a2", ids)
    check("最旧的排最后（a4 = 60 天前）", ids[-1] == "a4", ids)
    check("排序不会漏条", len(ids) == 6, ids)

    print("[4] 排序：截止时间（近→远），已过期的和没日期的都沉底")
    ids = [r["job_id"] for r in db.query(active_only=False, sort="截止时间（近→远）")]
    check("最先截止的排最前（a3 = 明天）", ids[0] == "a3", ids)
    check("第二是临期 2 天的 a1", ids[1] == "a1", ids)
    check("没有截止日期的排在最后（不能顶掉快截止的）", ids[-1] == "a4", ids)
    check("已截止的 a5 排在没过期的后面", ids.index("a5") > ids.index("a2"), ids)

    print("[5] 排序：公司名（A→Z）")
    names = [r["company"] for r in db.query(active_only=False, sort="公司名（A→Z）")]
    check("按公司名升序（SQLite 按 UTF-8 字节序，中文即拼音序）",
          names == sorted(names), names)
    check("第一条是『中国航空…』（中 < 云、北 按码位）", names[0].startswith("中国航空"), names[0])
    check("『中国…』排在『云南…』前面", names.index(names[0]) < len(names), names)

    print("[6] 排序白名单（拼 SQL 前必须过滤，不能被注入）")
    evil = db.query(active_only=False, sort="id; DROP TABLE jobs")
    check("非法排序键不会炸，退回默认顺序", len(evil) == 6, len(evil))
    check("jobs 表还在", len(db.query(active_only=False)) == 6)

    print("[7] 城市多选（昆明 + 大理）")
    got = sorted({r["city"] for r in db.query(active_only=False, cities=["昆明", "大理"])})
    check("只出昆明和大理", got == ["大理", "昆明"], got)
    check("昆明+大理 共 4 条", len(db.query(active_only=False, cities=["昆明", "大理"])) == 4)
    check("只选大理 = 2 条", len(db.query(active_only=False, cities=["大理"])) == 2)
    check("不选城市 = 全部 6 条", len(db.query(active_only=False, cities=[])) == 6)
    check("选『云南』会展开成州市（昆明/大理/曲靖 都在）",
          len(db.query(active_only=False, cities=["云南"])) == 5,
          len(db.query(active_only=False, cities=["云南"])))
    check("city 参数误传列表也不会炸（容错）",
          len(db.query(active_only=False, city=["大理"])) == 2,
          len(db.query(active_only=False, city=["大理"])))

    print("[8] 报名中（🟢）= 有截止日期且没过期")
    op = db.query(active_only=False, open_only=True)
    ids = sorted(r["job_id"] for r in op)
    check("报名中只含有截止日期且未过期的", ids == ["a1", "a2", "a3", "a6"], ids)
    check("已截止的 a5 被排除", "a5" not in ids, ids)
    check("没写截止日期的 a4 不算报名中", "a4" not in ids, ids)
    conn = db.connect()
    conn.execute("UPDATE jobs SET deadline=? WHERE job_id='a5'", (d(20),))
    conn.commit(); conn.close()
    check("把 a5 的截止日改到将来 → 它就变成报名中了",
          "a5" in [r["job_id"] for r in db.query(active_only=False, open_only=True)])

    print("[9] 剩余天数 / 临期标红")
    import app as app_mod
    check("剩 1 天 → 红色", app_mod.left_badge(1) == ("剩 1 天", "#d1242f"), app_mod.left_badge(1))
    check("剩 3 天 → 还是红色（临期 3 天标红）",
          app_mod.left_badge(3) == ("剩 3 天", "#d1242f"), app_mod.left_badge(3))
    check("剩 4 天 → 不再是红色", app_mod.left_badge(4)[1] != "#d1242f", app_mod.left_badge(4))
    check("今天截止 → 『今天截止』且红色",
          app_mod.left_badge(0)[0] == "今天截止", app_mod.left_badge(0))
    check("已过 → 『已截止』灰色", app_mod.left_badge(-2)[0] == "已截止", app_mod.left_badge(-2))
    check("没截止日期 → 『—』", app_mod.left_badge(None)[0] == "—", app_mod.left_badge(None))
    check("days_left 认得 YYYY-MM-DD", app_mod.days_left(d(5)) == 5, app_mod.days_left(d(5)))
    check("days_left 对空值返回 None", app_mod.days_left("") is None, app_mod.days_left(""))

    print("[10] 卡片 HTML：发布时间 / 截止 / 剩余 都在")
    r = [x for x in db.query(active_only=False) if x["job_id"] == "a3"][0]
    html = app_mod._card_html(r)
    check("卡片里有岗位名", "运维工程师" in html)
    check("卡片里有公司名", "云南电网" in html)
    check("卡片里有发布时间", "发布 " in html, html[:120])
    check("卡片里有截止日期", "截止 " in html)
    check("临期 1 天 → 卡片出现红色告警徽章", "#d1242f" in html and "剩 1 天" in html)
    check("卡片里有投递链接", 'href=' in html and 'target="_blank"' in html)
    r4 = [x for x in db.query(active_only=False) if x["job_id"] == "a4"][0]
    html4 = app_mod._card_html(r4)
    check("没截止日期的卡片显示『未公布』而不是报错", "未公布" in html4, html4[:200])
    check("抓取日兜底的会标注（卡片里）", "（抓取日）" in app_mod._card_html(a5), None)
    check("公司名带尖括号也不会毁掉页面（转义）",
          "&lt;script&gt;" in app_mod._card_html(dict(r, company="<script>")), None)

    print("[11] 关键词筛选仍然生效")
    check("搜『嵌入式』1 条", len(db.query(active_only=False, keyword="嵌入式")) == 1)
    check("搜『工程师』3 条", len(db.query(active_only=False, keyword="工程师")) == 3,
          len(db.query(active_only=False, keyword="工程师")))

    for p in (tmp_db, tmp_db + "-wal", tmp_db + "-shm"):
        try:
            os.remove(p)
        except OSError:
            pass
    shutil.rmtree(tmpdir, ignore_errors=True)
    print(f"\n结果: {PASS} 通过, {FAIL} 失败")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
