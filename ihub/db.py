"""SQLite 数据层：建表、去重写入、查询、收藏。"""
import os
import sqlite3
import datetime

from . import config
from . import channels
from .filters import scan_job

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL DEFAULT '实习僧',
    job_id TEXT,                 -- 来源端唯一 id（如 inn_xxx）
    title TEXT,
    company TEXT,
    city TEXT,
    salary TEXT,                 -- 展示用薪资
    salary_min INTEGER,
    salary_max INTEGER,
    degree TEXT,                 -- 学历要求
    duration TEXT,               -- 实习时长
    tags TEXT,                   -- 标签（逗号分隔）
    industry TEXT,
    link TEXT,                   -- 原始官方链接
    fetched_at TEXT,
    updated_at TEXT,
    is_active INTEGER DEFAULT 1, -- 1 有效；0 过期/失效
    is_fake INTEGER DEFAULT 0,   -- 1 疑似风险
    fake_reason TEXT DEFAULT '',
    favorite INTEGER DEFAULT 0,  -- 收藏
    deadline TEXT,               -- 报名/截止日期 YYYY-MM-DD（来自详情页，可能为空）
    published_at TEXT,           -- 来源发布日期（多数平台不公开，可为空）
    apply_state INTEGER DEFAULT 0, -- 投递状态：0=未投；1=投递箱(待投)；2=已投
    apply_note TEXT DEFAULT '',  -- 针对该岗位生成的投递理由
    official_url TEXT DEFAULT '', -- 企业官方招聘入口（核验/直达用，可空）
    job_type TEXT DEFAULT '实习', -- 实习 / 秋招 / 校招
    batch TEXT DEFAULT '',        -- 届别，如 2027届
    description TEXT DEFAULT '',  -- 备注/描述（采集表格里未识别的列会归到这里）
    dedup_key TEXT               -- 跨平台去重键（预留）
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_src_job ON jobs(source, job_id);
CREATE INDEX IF NOT EXISTS idx_city ON jobs(city);
CREATE INDEX IF NOT EXISTS idx_active ON jobs(is_active);

-- 网申跟踪表（秋招/实习投递进度）
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_ref INTEGER,                 -- 关联 jobs.id（手动添加时为空）
    company TEXT, title TEXT, city TEXT, url TEXT,
    job_type TEXT DEFAULT '秋招',
    stage TEXT DEFAULT '未投',        -- 未投/已投/笔试/面试/Offer/未通过
    deadline TEXT, applied_at TEXT, updated_at TEXT,
    note TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_app_stage ON applications(stage);
"""


def now_str():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def connect():
    os.makedirs(os.path.dirname(config.DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def backfill_official_urls() -> int:
    """为已有岗位按公司名回填企业官网招聘入口。"""
    conn = connect()
    rows = conn.execute(
        "SELECT id, company FROM jobs WHERE official_url IS NULL OR official_url=''").fetchall()
    n = 0
    for r in rows:
        u = channels.official_for(str(r["company"] or ""))
        if u:
            conn.execute("UPDATE jobs SET official_url=? WHERE id=?", (u, r["id"]))
            n += 1
    conn.commit()
    conn.close()
    return n


def init_db():
    """建表 + 增量迁移（为老库补充新列）。"""
    conn = connect()
    conn.executescript(_SCHEMA)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    for col, decl in (("deadline", "TEXT"), ("published_at", "TEXT"),
                      ("apply_state", "INTEGER DEFAULT 0"), ("apply_note", "TEXT DEFAULT ''"),
                      ("official_url", "TEXT DEFAULT ''"), ("job_type", "TEXT DEFAULT '实习'"),
                      ("batch", "TEXT DEFAULT ''"),
                      ("description", "TEXT DEFAULT ''")):
        if col not in cols:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {col} {decl}")
    # 迁移完成后才建涉及新列的索引
    conn.execute("CREATE INDEX IF NOT EXISTS idx_deadline ON jobs(deadline)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_apply ON jobs(apply_state)")
    conn.commit()
    conn.close()


def upsert_jobs(jobs: list) -> dict:
    """把抓到的岗位写入库：去重（来源+job_id），打风险标签。

    jobs: list[dict]，字段见 crawlers/base.py 的 field map。
    返回 {"inserted": n, "updated": m, "skipped_dup": k, "flagged": f}
    """
    conn = connect()
    now = now_str()
    res = {"inserted": 0, "updated": 0, "skipped_dup": 0, "flagged": 0}
    for j in jobs:
        try:
            is_fake, reason = scan_job(j)
            job_id = str(j.get("job_id") or "")
            cur = conn.execute(
                "SELECT id, is_fake FROM jobs WHERE source=? AND job_id=?",
                (j.get("source", "实习僧"), job_id))
            row = cur.fetchone()
            official = str(j.get("official_url") or "") or channels.official_for(str(j.get("company") or ""))
            jtype = str(j.get("job_type") or "实习")
            batch = str(j.get("batch") or "")
            vals = (
                j.get("source", "实习僧"), job_id, j.get("title"), j.get("company"),
                j.get("city"), j.get("salary"), j.get("salary_min"), j.get("salary_max"),
                j.get("degree"), j.get("duration"), j.get("tags"), j.get("industry"),
                j.get("link"), now, now,
                1, int(is_fake), reason, 0,
                j.get("deadline"), j.get("published_at"), official,
                jtype, batch,
                str(j.get("description") or ""),
                j.get("dedup_key"),
            )
            if row is None:
                conn.execute(
                    """INSERT INTO jobs (source, job_id, title, company, city, salary,
                       salary_min, salary_max, degree, duration, tags, industry, link,
                       fetched_at, updated_at, is_active, is_fake, fake_reason, favorite,
                       deadline, published_at, official_url, job_type, batch, description,
                       dedup_key)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", vals)
                res["inserted"] += 1
            else:
                # 已有记录：更新内容；风险标记取“任一来源判定为风险”则标风险
                conn.execute(
                    """UPDATE jobs SET title=?, company=?, city=?, salary=?, salary_min=?,
                       salary_max=?, degree=?, duration=?, tags=?, industry=?, link=?,
                       updated_at=?, is_active=1,
                       deadline = COALESCE(?, deadline),
                       published_at = COALESCE(?, published_at),
                       official_url = COALESCE(?, official_url),
                       job_type = CASE WHEN ?!='' THEN ? ELSE job_type END,
                       batch = CASE WHEN ?!='' THEN ? ELSE batch END,
                       description = CASE WHEN ?!='' THEN ? ELSE description END,
                       is_fake = MAX(is_fake, ?), fake_reason = CASE WHEN is_fake=1 THEN fake_reason ELSE ? END
                       WHERE source=? AND job_id=?""",
                    (j.get("title"), j.get("company"), j.get("city"), j.get("salary"),
                     j.get("salary_min"), j.get("salary_max"), j.get("degree"),
                     j.get("duration"), j.get("tags"), j.get("industry"), j.get("link"),
                     now, j.get("deadline"), j.get("published_at"), official,
                     jtype, jtype, batch, batch,
                     str(j.get("description") or ""), str(j.get("description") or ""),
                     int(is_fake), reason, j.get("source", "实习僧"), job_id))
                res["updated"] += 1
            if is_fake:
                res["flagged"] += 1
        except Exception:
            continue
    conn.commit()
    conn.close()
    return res


def query(city=None, keyword=None, active_only=True, fake_only=False,
          favorite_only=False, unexpired_only=False, since_days=None,
          apply_state=None, job_type=None, limit=2000, order="id DESC"):
    """查询岗位；city/keyword 支持包含匹配。apply_state: 0未投/1待投/2已投/None不限。
    job_type: 实习/秋招/校招/None不限。"""
    conn = connect()
    sql = "SELECT * FROM jobs WHERE 1=1"
    params = []
    if active_only:
        sql += " AND is_active=1"
    if job_type and job_type != "全部":
        sql += " AND job_type=?"
        params.append(job_type)
    if fake_only:
        sql += " AND is_fake=1"
    if favorite_only:
        sql += " AND favorite=1"
    if apply_state is not None:
        sql += " AND apply_state=?"
        params.append(int(apply_state))
    if unexpired_only:
        sql += " AND (deadline IS NULL OR deadline = '' OR deadline >= date('now', 'localtime'))"
    if since_days:
        sql += " AND fetched_at >= date('now', 'localtime', ?)"
        params.append(f"-{int(since_days)} days")
    if city:
        cities = config.PROVINCE_CITIES.get(city, [city])
        if len(cities) == 1:
            sql += " AND city LIKE ?"
            params.append(f"%{cities[0]}%")
        else:
            placeholders = ",".join("?" * len(cities))
            sql += f" AND city IN ({placeholders})"
            params.extend(cities)
    if keyword:
        like = f"%{keyword}%"
        sql += " AND (title LIKE ? OR company LIKE ? OR tags LIKE ? OR industry LIKE ?)"
        params += [like, like, like, like]
    sql += f" ORDER BY {order} LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def distinct_cities():
    conn = connect()
    rows = conn.execute("SELECT DISTINCT city FROM jobs WHERE city!='' ORDER BY city").fetchall()
    conn.close()
    return [r["city"] for r in rows]


def stats():
    conn = connect()
    total = conn.execute("SELECT COUNT(*) c FROM jobs").fetchone()["c"]
    active = conn.execute("SELECT COUNT(*) c FROM jobs WHERE is_active=1").fetchone()["c"]
    fav = conn.execute("SELECT COUNT(*) c FROM jobs WHERE favorite=1").fetchone()["c"]
    fake = conn.execute("SELECT COUNT(*) c FROM jobs WHERE is_fake=1").fetchone()["c"]
    last = conn.execute("SELECT MAX(updated_at) m FROM jobs").fetchone()["m"]
    conn.close()
    return {"total": total, "active": active, "favorite": fav, "fake": fake, "last_update": last}


def set_favorites(ids):
    conn = connect()
    conn.execute("UPDATE jobs SET favorite=0")
    if ids:
        conn.executemany("UPDATE jobs SET favorite=1 WHERE id=?", [(i,) for i in ids])
    conn.commit()
    conn.close()


def set_apply_state(id_state_pairs):
    """id_state_pairs: [(job_id, state)] state: 0未投/1待投/2已投。"""
    conn = connect()
    conn.executemany("UPDATE jobs SET apply_state=? WHERE id=?",
                     [(st, i) for i, st in id_state_pairs])
    conn.commit()
    conn.close()


def set_apply_note(job_id, note):
    conn = connect()
    conn.execute("UPDATE jobs SET apply_note=? WHERE id=?", (note, job_id))
    conn.commit()
    conn.close()


# ==================== 网申跟踪 ====================
STAGES = ["未投", "已投", "笔试", "面试", "Offer", "未通过"]


def app_add(company="", title="", city="", url="", job_type="秋招", deadline="", note="", job_ref=None):
    conn = connect()
    now = now_str()
    cur = conn.execute(
        """INSERT INTO applications (job_ref, company, title, city, url, job_type, stage,
           deadline, applied_at, updated_at, note) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (job_ref, company, title, city, url, job_type, "未投", deadline, "", now, note))
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def app_add_from_job_ids(ids):
    """把岗位库里的岗位批量加入网申跟踪（已存在的跳过）。"""
    conn = connect()
    now = now_str()
    added = 0
    for jid in ids:
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()
        if not row:
            continue
        exists = conn.execute("SELECT id FROM applications WHERE job_ref=?", (jid,)).fetchone()
        if exists:
            continue
        conn.execute(
            """INSERT INTO applications (job_ref, company, title, city, url, job_type, stage,
               deadline, applied_at, updated_at, note) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (jid, row["company"], row["title"], row["city"], row["official_url"] or row["link"],
             row["job_type"] or "实习", "未投", row["deadline"] or "", "", now, ""))
        added += 1
    conn.commit()
    conn.close()
    return added


def app_list(stage=None, keyword=None, limit=1000):
    conn = connect()
    sql = "SELECT * FROM applications WHERE 1=1"
    params = []
    if stage and stage != "全部":
        sql += " AND stage=?"
        params.append(stage)
    if keyword:
        like = f"%{keyword}%"
        sql += " AND (company LIKE ? OR title LIKE ? OR city LIKE ? OR note LIKE ?)"
        params += [like, like, like, like]
    sql += " ORDER BY CASE stage WHEN '未投' THEN 0 WHEN '已投' THEN 1 WHEN '笔试' THEN 2 WHEN '面试' THEN 3 ELSE 4 END, id DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def app_update(app_id, stage=None, deadline=None, note=None, url=None):
    conn = connect()
    now = now_str()
    sets, params = ["updated_at=?"], [now]
    if stage is not None:
        sets.append("stage=?")
        params.append(stage)
        if stage != "未投":
            sets.append("applied_at=COALESCE(NULLIF(applied_at,''), ?)")
            params.append(now[:10])
        else:
            sets.append("applied_at=''")
    for col, val in (("deadline", deadline), ("note", note), ("url", url)):
        if val is not None:
            sets.append(f"{col}=?")
            params.append(val)
    params.append(app_id)
    conn.execute(f"UPDATE applications SET {', '.join(sets)} WHERE id=?", params)
    conn.commit()
    conn.close()


def app_delete(app_id):
    conn = connect()
    conn.execute("DELETE FROM applications WHERE id=?", (app_id,))
    conn.commit()
    conn.close()


def app_stats():
    conn = connect()
    rows = conn.execute("SELECT stage, COUNT(*) c FROM applications GROUP BY stage").fetchall()
    conn.close()
    out = {s: 0 for s in STAGES}
    for r in rows:
        out[r["stage"]] = r["c"]
    return out
