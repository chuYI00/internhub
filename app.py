"""Streamlit 网页：实习岗位聚合器 InternHub + 投递工作台
运行：streamlit run app.py  →  http://localhost:8501
"""
import csv
import datetime
import os
import re

import pandas as pd
import streamlit as st

from ihub import config, db
from ihub.linklist import apply_links_text

ROOT_APP = config.PROJECT_ROOT
from ihub.crawlers import CRAWLERS

OUT_DIR = os.path.join(config.PROJECT_ROOT, "投递文件")

st.set_page_config(page_title="实习岗位聚合器 InternHub", page_icon="🧭", layout="wide")

DISCLAIMER = ("本工具仅聚合网络公开岗位信息，不参与招聘，不对岗位真实性、合法性做担保；"
              "请点击【投递链接】前往原始官方页面核实后再投递。谨防付费内推/培训费/押金类骗局。")
AUTOBOT_NOTE = ("⚠️ 平台禁止脚本自动投递（会封号），本工具不自动提交申请："
                "你在下方把材料准备好后，**点官方链接手动投递**，再回来标记“已投”。")


def _display_df(rows):
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["标签"] = df["tags"]
    df["截止时间"] = df.get("deadline", pd.Series(dtype=str)).fillna("")
    df["收录时间"] = df.get("fetched_at", pd.Series(dtype=str)).fillna("")
    df["投递箱"] = df.get("apply_state", pd.Series(dtype=int)).fillna(0).astype(int) >= 1
    df["favorite"] = df.get("favorite", pd.Series(dtype=int)).fillna(0).astype(int) > 0
    df["企业官网"] = df.get("official_url", pd.Series(dtype=str)).fillna("")
    return df


def load_df(city, keyword, active_only, fake_only, favorite_only,
            unexpired_only, since_days, job_type=None):
    rows = db.query(city=city, keyword=keyword, active_only=active_only,
                    fake_only=fake_only, favorite_only=favorite_only,
                    unexpired_only=unexpired_only, since_days=since_days,
                    job_type=job_type)
    return _display_df(rows)


def export_box_csv():
    rows = db.query(apply_state=1)
    if not rows:
        return None
    path = os.path.join(OUT_DIR, f"投递清单_{datetime.date.today().isoformat()}.csv")
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["岗位", "公司", "城市", "薪资", "截止日期", "来源", "官方投递入口", "原平台链接"])
        for r in rows:
            w.writerow([r["title"], r["company"], r["city"], r["salary"],
                        r.get("deadline") or "", r["source"],
                        r.get("official_url") or "", r["link"]])
    return path


def gen_resume_for(job, jd_text=None):
    from ihub import resume
    safe = resume.safe_name(str(job.get("company") or "") + "_" + str(job.get("title") or ""))
    path = os.path.join(OUT_DIR, f"{safe}_简历.docx")
    return resume.build_docx(job, path, jd_text=jd_text)


def _applied_index():
    """已投（进度不是"未投"）的记录 → {(公司, 岗位): [记录]}，用于重复投递检查。"""
    idx = {}
    try:
        for r in db.app_list(limit=2000):
            if (r.get("stage") or "未投") == "未投":
                continue
            key = (str(r.get("company") or "").strip(), str(r.get("title") or "").strip())
            idx.setdefault(key, []).append(r)
    except Exception:
        pass
    return idx


def _dup_hits(company, title, idx=None):
    """这条岗位我是不是已经投过了？（同名公司 + 岗位名互相包含即算命中）"""
    idx = idx if idx is not None else _applied_index()
    c, t = str(company or "").strip(), str(title or "").strip()
    hits = []
    for (kc, kt), rows in idx.items():
        if not kc:
            continue
        same_co = (kc == c) or (c and (kc in c or c in kc))
        if not same_co:
            continue
        same_jt = (not kt) or (not t) or (kt == t) or (kt in t) or (t in kt)
        if same_jt:
            hits += rows
    return hits


def _download_file(path, label, mime, container=None):
    """存在才显示下载按钮；不存在就提示怎么生成。container 可传 st.columns 里的某一列。"""
    box = container if container is not None else st
    if not os.path.exists(path):
        box.button(label + "（未生成）", disabled=True, key="miss_" + os.path.basename(path))
        box.caption("先跑一次：`venv\\Scripts\\python.exe gen_resume_kit.py`")
        return
    with open(path, "rb") as f:
        data = f.read()
    box.download_button(label, data=data, file_name=os.path.basename(path), mime=mime,
                        key="dl_" + os.path.basename(path))


def main():
    st.title("🧭 实习岗位聚合器 InternHub")
    st.caption("聚合公开实习信息 · 投递材料按岗位定制 · 本地个人学习使用")

    db.init_db()
    db.backfill_official_urls()

    with st.sidebar:
        st.header("① 抓取设置")
        src_name = st.selectbox("数据源", list(CRAWLERS.keys()))
        known = db.distinct_cities()
        ordered = config.DEFAULT_CITIES + known
        seen = set()
        city_options = [c for c in ordered if not (c in seen or seen.add(c))]
        default_candidates = [c for c in config.DEFAULT_CITIES if c in known]
        default_cities = default_candidates[:3] if default_candidates else config.DEFAULT_CITIES[:2]
        cities = st.multiselect("城市（抓取与展示）", city_options, default=default_cities)
        pages = st.slider("每城市抓取页数（每页约20条，建议≤3）", 1, 5, min(config.DEFAULT_PAGES, 3))
        enrich = st.checkbox("同时抓详情页“截止时间”（慢，只补前15条）")
        if st.button("🚀 立即抓取", type="primary"):
            crawler = CRAWLERS[src_name]()
            bar = st.progress(0.0)
            jobs = []
            # 多源/RSS 类数据源与城市无关：只跑一次
            once = any(k in src_name for k in ("多源", "RSS"))
            targets = ["(全部源)"] if once else cities
            for i, c in enumerate(targets, 1):
                with st.spinner(f"抓取 {c}…"):
                    jobs += crawler.fetch_city(c if not once else "", max_pages=pages)
                bar.progress(i / max(1, len(targets)))
            if enrich and jobs and hasattr(crawler, "enrich_deadlines"):
                with st.spinner("补抓截止时间（详情页）…"):
                    crawler.enrich_deadlines(jobs, cap=min(15, len(jobs)))
            res = db.upsert_jobs(jobs)
            st.success(f"解析 {len(jobs)} 条 → 新增 {res['inserted']} / 更新 {res['updated']}")
            st.rerun()

        st.divider()
        st.header("② 筛选")
        city_choices = list(dict.fromkeys(["全部"] + config.PROVINCE_LABELS + sorted(db.distinct_cities())))
        quick = st.radio("快速锁定城市（秋招用）", ["不限", "潍坊", "昆明", "大理"], horizontal=True)
        f_city = st.selectbox("按地区筛选（支持省份，如“山东/云南”）", city_choices)
        if quick != "不限":
            f_city = quick
        job_type = st.radio("岗位类型", ["全部", "实习", "秋招"], horizontal=True)
        f_keyword = st.text_input("关键词（岗位/公司/标签）", placeholder="例如：国企 / 电气 / 嵌入式 / 新媒体")
        c1, c2 = st.columns(2)
        active_only = c1.checkbox("仅看有效", value=True)
        fake_only = c2.checkbox("只看风险标记")
        fav_only = st.checkbox("只看收藏")
        unexpired = st.checkbox("只看未截止（有截止日期的过滤）", value=True)
        time_range = st.radio("收录时间范围", ["全部", "近3天", "近7天", "近30天"], horizontal=True)
        since_days = {"近3天": 3, "近7天": 7, "近30天": 30}.get(time_range)

    s = db.stats()
    in_box = db.query(apply_state=1)
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("累计入库", s["total"])
    m2.metric("有效岗位", s["active"])
    m3.metric("投递箱", len(in_box))
    m4.metric("收藏", s["favorite"])
    m5.metric("最近更新", (s["last_update"] or "—")[5:16])

    if s["fake"]:
        st.warning(f"已标记 {s['fake']} 条疑似风险岗位，可在侧边栏勾选“只看风险标记”核对。")

    (tab1, tab2, tab3, tab4, tab5, tab6,
     tab7, tab8, tab9, tab10, tab11, tab12) = st.tabs(
        ["岗位列表", "🏆 为你推荐", "🎯 投递工作台", "我的收藏", "👤 我的资料", "📮 网申跟踪",
         "🛰 秋招渠道", "📚 备考方案", "📝 简历定制", "🌏 云南秋招", "🍃 烟草监控", "说明与合规"])

    # ============ 岗位列表 ============
    with tab1:
        city_arg = None if f_city == "全部" else f_city
        df = load_df(city_arg, f_keyword or None, active_only, fake_only, fav_only,
                     unexpired, since_days, job_type=job_type)
        if df.empty:
            st.info("📭 暂无数据：先在左侧选城市并点「立即抓取」。")
        else:
            today = datetime.date.today().isoformat()
            dl = df["截止时间"].astype(str).str[:10]
            df["状态"] = dl.apply(lambda x: "已截止" if (len(x) == 10 and x < today) else ("临近" if (len(x) == 10 and x <= today) else "可投"))
            st.caption(f"共 {len(df)} 条 · 勾选「投递箱」→ 保存后到「投递工作台」生成材料")
            cols = ["id", "title", "company", "city", "salary", "degree", "标签",
                    "截止时间", "状态", "投递箱", "source", "link", "企业官网", "favorite"]
            edit = st.data_editor(
                df[cols],
                hide_index=True,
                disabled=[c for c in cols if c not in ("投递箱", "favorite")],
                column_config={
                    "id": None,
                    "title": st.column_config.TextColumn("岗位"),
                    "company": "公司", "city": "城市", "salary": "薪资", "degree": "学历",
                    "标签": "标签",
                    "截止时间": "截止时间",
                    "状态": "状态",
                    "投递箱": st.column_config.CheckboxColumn("🎯投递箱", help="勾选后到“投递工作台”批量准备材料"),
                    "source": "来源",
                    "link": st.column_config.LinkColumn("投递（原平台）", help="岗位来源平台的原始详情页/申请链接"),
                    "企业官网": st.column_config.LinkColumn("企业官网招聘", help="公司官方招聘入口（核验/直达用，缺省为空）"),
                    "favorite": st.column_config.CheckboxColumn("⭐收藏"),
                },
                num_rows="fixed", width="stretch", height=560,
            )
            if st.button("💾 保存 投递箱+收藏", type="primary"):
                fav_ids = edit.loc[edit["favorite"] == True, "id"].tolist()  # noqa: E712
                db.set_favorites(fav_ids)
                pairs = [(int(x), int(bool(y))) for x, y in zip(edit["id"], edit["投递箱"])]
                db.set_apply_state(pairs)
                st.success(f"已更新：收藏 {len(fav_ids)} 条；投递箱 {sum(1 for _, v in pairs if v)} 条")
                st.rerun()

            st.divider()
            st.markdown("**🚀 广投：把「当前筛选结果」整批处理（昆明/大理 秋招适用）**")
            st.caption(f"当前筛选出 **{len(df)}** 条。下面按钮作用于这 {len(df)} 条，不用一条条勾选。")
            b1, b2, b3, b4 = st.columns([1.2, 0.9, 0.9, 1.1])
            if b1.button("🚀 全部加入投递箱", type="primary", key="bulk_in"):
                db.set_apply_state([(int(i), 1) for i in df["id"]])
                st.success(f"已把 {len(df)} 条加入投递箱 → 去「🎯 投递工作台」批量生成材料")
                st.rerun()
            if b2.button("➖ 全部移出投递箱", key="bulk_out"):
                db.set_apply_state([(int(i), 0) for i in df["id"]])
                st.success(f"已把 {len(df)} 条移出投递箱")
                st.rerun()
            export = df[["title", "company", "city", "salary", "degree", "截止时间", "状态",
                          "企业官网", "link"]].copy()
            export.columns = ["岗位", "公司", "城市", "薪资", "学历", "截止日期", "状态",
                              "官方投递入口", "原平台链接"]
            b3.download_button(
                "⬇️ 导出清单 CSV",
                export.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"广投清单_{f_city}_{job_type}_{datetime.date.today().isoformat()}.csv",
                mime="text/csv", key="bulk_export",
                help="带投递链接，可用 Excel/WPS 打开打印，投一个划掉一个")
            if b4.download_button(
                "⬇️ 官方投递入口清单",
                apply_links_text(df.to_dict("records")).encode("utf-8"),
                file_name=f"投递入口清单_{f_city}_{job_type}_{datetime.date.today().isoformat()}.txt",
                mime="text/plain", key="bulk_links",
                help="每条岗位一段：企业官方投递页（能直达网申系统）+ 原平台链接，手机上也能按着投",
            ):
                st.toast("已生成：投递入口清单（含官方网申入口）")

    # ============ 🏆 为你推荐 ============
    with tab2:
        st.markdown("#### 🏆 岗位推荐（钱多 / 轻松 / 专业契合 综合打分）")
        from ihub import prefs as prefs_mod, match
        p = prefs_mod.load()
        c1, c2, c3 = st.columns(3)
        p["w_salary"] = c1.slider("「钱多」权重", 0.0, 1.0, float(p.get("w_salary", 0.4)), 0.05)
        p["w_match"] = c2.slider("「专业契合」权重", 0.0, 1.0, float(p.get("w_match", 0.35)), 0.05)
        p["w_easy"] = c3.slider("「轻松」权重", 0.0, 1.0, float(p.get("w_easy", 0.25)), 0.05)
        c4, c5 = st.columns([1, 2])
        p["min_salary"] = c4.number_input("期望最低日薪（元/天）", 0, 1000, int(p.get("min_salary", 100)), 10)
        top_n = c5.slider("展示条数", 10, 200, 30, 10)
        with st.expander("⚙️ 关键词设置（决定「契合」与「轻松」怎么算）"):
            p["major_keywords"] = prefs_mod.lists(st.text_area(
                "专业契合关键词（逗号分隔）", value="，".join(p.get("major_keywords", [])), height=68))
            p["easy_tags"] = prefs_mod.lists(st.text_area(
                "轻松信号（逗号分隔）", value="，".join(p.get("easy_tags", [])), height=68))
            p["hard_keywords"] = prefs_mod.lists(st.text_area(
                "强度/避雷关键词（逗号分隔）", value="，".join(p.get("hard_keywords", [])), height=68))
            if st.button("💾 保存偏好"):
                st.success(f"已保存：{prefs_mod.save(p)}")

        city_arg_r = None if f_city == "全部" else f_city
        rows_r = db.query(city=city_arg_r, keyword=f_keyword or None, active_only=active_only,
                          unexpired_only=unexpired, since_days=since_days,
                          job_type=job_type, limit=3000)
        if not rows_r:
            st.info("暂无数据：先在左侧选城市并点「🚀 立即抓取」。")
        else:
            ranked = match.rank(rows_r, p, top=top_n)
            dfr = pd.DataFrame(ranked)
            dfr["截止时间"] = dfr.get("deadline", pd.Series(dtype=str)).fillna("")
            dfr["企业官网"] = dfr.get("official_url", pd.Series(dtype=str)).fillna("")
            st.caption("打分依据：薪资数字 + 岗位标签/标题关键词（启发式）。**不代表真实工作强度**，仅用于快速初筛，投递前请自行判断。")
            st.dataframe(
                dfr[["score", "title", "company", "city", "salary", "s_easy", "s_match", "s_salary",
                     "reason", "截止时间", "link", "企业官网"]],
                hide_index=True,
                column_config={
                    "score": st.column_config.ProgressColumn("匹配分", min_value=0, max_value=100, format="%d"),
                    "title": "岗位", "company": "公司", "city": "城市", "salary": "薪资",
                    "s_easy": st.column_config.NumberColumn("轻松分", format="%d"),
                    "s_match": st.column_config.NumberColumn("契合分", format="%d"),
                    "s_salary": st.column_config.NumberColumn("薪资分", format="%d"),
                    "reason": st.column_config.TextColumn("推荐理由", width="large"),
                    "截止时间": "截止时间",
                    "link": st.column_config.LinkColumn("投递（原平台）"),
                    "企业官网": st.column_config.LinkColumn("企业官网招聘"),
                },
                width="stretch", height=620,
            )

    # ============ 投递工作台 ============
    with tab3:
        st.warning(AUTOBOT_NOTE)
        scope = st.radio("查看", ["🎯 投递箱（待投）", "✅ 已投记录"], horizontal=True)
        state = 1 if "投递箱" in scope else 2
        rows = db.query(apply_state=state, active_only=False, limit=400)
        if not rows:
            hint = ("投递箱是空的：到“岗位列表”勾选 🎯 后点「保存 投递箱+收藏」。"
                    if state == 1 else "还没有已投记录：在投递箱逐条处理并点「✅ 标记已投」后会出现这里。")
            st.info(hint)
        else:
            if state == 1 and st.button("📤 导出投递清单 CSV"):
                p = export_box_csv()
                st.success(f"已导出：{p}")
            st.caption(f"{'投递箱（待投）' if state == 1 else '已投'} 共 {len(rows)} 条，逐条处理：")
            for job in rows:
                title = str(job.get("title") or "")
                mark = "✅" if state == 2 else "🎯"
                with st.expander(f"{mark}【{job.get('company')}】{title[:36]}｜{job.get('city')}｜{job.get('salary') or '—'}"):
                    line = f"原平台投递：{job.get('link')}"
                    if job.get("official_url"):
                        line += f"\n\n企业官网招聘：{job['official_url']}（投递前建议先到官网核验）"
                    st.markdown(line)
                    _hits = _dup_hits(job.get("company"), job.get("title"))
                    if _hits:
                        st.warning("⚠️ 你**已经投过**同岗位："
                                   + "、".join(f'{h.get("company")}｜{h.get("title")}（{h.get("stage")}，'
                                               f'{h.get("applied_at") or "日期未记"}）' for h in _hits[:3])
                                   + "　—— 别重复投，尤其是烟草按批次限报。")
                    from ihub import resume
                    note = job.get("apply_note") or resume.apply_message(job)
                    edited = st.text_area("投递理由/开场白（可改）", value=note,
                                          key=f"note_{job['id']}_{state}", height=130)
                    jd_text = st.text_area(
                        "（可选）粘贴该岗位 JD / 任职要求 → 生成更贴岗位的简历",
                        key=f"jd_{job['id']}", height=110,
                        placeholder="把招聘页面的“岗位职责/任职要求”整段粘进来即可")
                    if jd_text:
                        try:
                            from ihub import resume as _rs
                            hit, miss = _rs.jd_analysis(jd_text)
                            st.caption(f"✅ 已覆盖：{'、'.join(hit) if hit else '—'}　|　"
                                       f"⚠️ 未覆盖（可考虑补充/学习）：{'、'.join(miss[:8]) if miss else '—'}")
                        except Exception:
                            pass
                    if state == 1:
                        c1, c2, c3, c4 = st.columns(4)
                        if c1.button("💾 保存理由", key=f"saven_{job['id']}"):
                            db.set_apply_note(job["id"], edited)
                            st.success("已保存")
                        if c2.button("📄 生成定制简历", key=f"cv_{job['id']}"):
                            try:
                                p = gen_resume_for(job, jd_text or None)
                                st.success(f"已生成：{p}")
                            except Exception as e:
                                st.error(f"生成失败：{e}")
                        if c3.button("✅ 标记已投", key=f"done_{job['id']}"):
                            db.set_apply_state([(job["id"], 2)])
                            st.rerun()
                        if c4.button("➖ 移出投递箱", key=f"out_{job['id']}"):
                            db.set_apply_state([(job["id"], 0)])
                            st.rerun()
                    else:
                        c1, c2 = st.columns(2)
                        if c1.button("↩ 取消已投（回到投递箱）", key=f"undone_{job['id']}", type="primary"):
                            db.set_apply_state([(job["id"], 1)])
                            st.rerun()
                        if c2.button("🗑 删除记录", key=f"del_{job['id']}"):
                            db.set_apply_state([(job["id"], 0)])
                            st.rerun()

    # ============ 我的收藏 ============
    with tab4:
        df_fav = load_df(None, None, active_only, False, True, unexpired, since_days)
        if df_fav.empty:
            st.info("还没有收藏。")
        else:
            st.dataframe(df_fav[["title", "company", "city", "salary", "截止时间", "source", "link"]],
                         hide_index=True,
                         column_config={"title": "岗位", "company": "公司", "city": "城市",
                                        "salary": "薪资", "截止时间": "截止时间", "source": "来源",
                                        "link": st.column_config.LinkColumn("投递链接（官方）")},
                         width="stretch")

    # ============ 👤 我的资料 ============
    with tab5:
        st.markdown("#### 👤 我的资料（生成投递材料时使用）")
        st.caption("资料只保存在本机 `data/profile.json`，不上传任何服务器。任何人使用本工具时，在这里换成自己的简历即可。")
        from ihub import profile as prof_mod
        cur = prof_mod.load()

        up = st.file_uploader("① 上传你的简历（.docx / .txt，可选）", type=["docx", "txt"])
        if up is not None:
            text = ""
            try:
                if up.name.lower().endswith(".docx"):
                    import io as _io
                    from docx import Document as _Doc
                    d = _Doc(_io.BytesIO(up.read()))
                    text = "\n".join(p.text for p in d.paragraphs)
                else:
                    text = up.read().decode("utf-8", "ignore")
            except Exception as e:
                st.error(f"读取失败：{e}")
            if text:
                guess = prof_mod.extract_from_text(text)
                st.success(f"已读取 {len(text)} 字；自动识别：{guess or '（未识别到关键信息，请手动填写）'}")
                st.session_state["uploaded_text"] = text
                for k, v in guess.items():
                    st.session_state[f"pf_{k}"] = v

        st.markdown("② 核对/修改字段（保存后即刻用于生成材料）")
        cols = st.columns(2)
        fields = [("name", "姓名"), ("gender", "性别"), ("city", "现居/生源地"),
                  ("phone", "电话"), ("email", "邮箱"), ("school", "学校"),
                  ("major", "专业"), ("degree", "学历"), ("edu_range", "在校时间"),
                  ("graduate_year", "毕业届别"), ("gpa", "GPA"), ("scholarship", "奖学金/荣誉"),
                  ("english", "英语/证书"), ("intent", "求职意向（一句话）")]
        newvals = {}
        for i, (k, label) in enumerate(fields):
            with cols[i % 2]:
                newvals[k] = st.text_input(label, value=st.session_state.get(f"pf_{k}", cur.get(k, "")),
                                           key=f"in_{k}")

        st.markdown("③ 多行内容（一行一条）")
        newvals["highlights"] = st.text_area("核心亮点（3-5 条）", value=cur.get("highlights", ""), height=110)
        newvals["skills"] = st.text_area("技能（一行一类）", value=cur.get("skills", ""), height=90)
        newvals["experiences"] = st.text_area(
            "实践/工作经历（每行：标题|时间|描述）", value=cur.get("experiences", ""), height=150)
        newvals["certificates"] = st.text_input("证书", value=cur.get("certificates", ""))
        newvals["self_eval"] = st.text_area("自我评价", value=cur.get("self_eval", ""), height=90)

        with st.expander("④ 网申补充字段（决定「网申助手」能自动填多少，建议都填上）", expanded=True):
            st.caption("这些是国内网申系统几乎必问的项，但简历上用不到，所以单独放这里。"
                       "**留空 = 自动跳过该字段**；也可以在网申页面的面板里当场补（存在本机浏览器）。")
            extra = [("birth", "出生日期（2005-03）"), ("political", "政治面貌"), ("nation", "民族"),
                     ("college", "学院"), ("enroll", "入学时间（2023.09）"), ("rank", "专业排名"),
                     ("hometown", "籍贯 / 生源地"), ("address", "通讯地址"), ("postal", "邮编"),
                     ("wechat", "微信号"), ("qq", "QQ 号"), ("idcard", "身份证号（敏感，可留空）"),
                     ("expected_city", "期望工作城市"), ("expected_salary", "期望薪资"),
                     ("available", "到岗时间 / 可实习时长"), ("marital", "婚姻状况"),
                     ("emergency_name", "紧急联系人"), ("emergency_phone", "紧急联系人电话"),
                     ("emergency_relation", "与本人关系")]
            ecols = st.columns(2)
            for i, (k, label) in enumerate(extra):
                with ecols[i % 2]:
                    newvals[k] = st.text_input(label, value=st.session_state.get(f"pf_{k}", cur.get(k, "")),
                                               key=f"in2_{k}")

        c1, c2 = st.columns([1, 3])
        if c1.button("💾 保存资料", type="primary"):
            p = prof_mod.save(newvals)
            st.success(f"已保存到：{p}（下一条投递材料就会用你的信息）")
        if c2.button("♻️ 恢复示例资料"):
            p = prof_mod.save(dict(prof_mod.DEFAULT))
            st.info("已恢复为内置示例资料（罗广睿）")

        st.divider()
        st.markdown("#### 📥 采集助手（把国聘 / 24365 / BOSS / 牛客等你已登录页面的岗位导出 CSV）")
        st.caption("为什么需要它：国家平台与商业平台都要登录、接口带签名，脚本抓不到；"
                   "但用**你自己已登录的浏览器**点一下按钮，就能把当前页面上的岗位导出成 CSV，再导入本工具统一管理。")
        if st.button("⬇️ 生成/更新 采集助手.user.js"):
            from ihub import collector
            path = collector.save_userscript()
            st.success(f"已生成：{path}")
        st.markdown("**用法**：① 已有 Tampermonkey（油猴）扩展 → ② 把这个 .user.js 拖进浏览器安装 → "
                    "③ 打开国聘/24365/BOSS/牛客的岗位列表页（登录状态、滚动加载完）→ ④ 点右下角 "
                    "**「📥 采集本页岗位」** 导出 CSV → ⑤ 到「📚 备考方案」页底部上传该 CSV，一键入库。")

        st.divider()
        st.markdown("#### 🧩 网申自动填写助手 v2（解决秋招网申一个个填很慢）")
        st.caption("在任意公司的网申页面右下角会出现**「📝 网申助手」**小按钮：点开是一个资料面板，"
                   "可以当场看到/补改每个字段，再选**「填入空字段」**或**「覆盖全部」**。"
                   "支持 text/textarea/**下拉框**/单选/日期/富文本，**表单在 iframe 里也能填**（很多网申系统就是这种）。"
                   "\n\n**不代登录、不代提交、不绕过验证码、不联网**：只在你点击时写你浏览器里已经打开的页面。")
        st.markdown("**安装步骤**：① 浏览器装 Tampermonkey（油猴）扩展 → ② 点下面按钮生成脚本 → "
                    "③ 把生成的文件拖进浏览器（或 Tampermonkey 里新建脚本粘贴内容）→ ④ 打开任意网申页面点右下角「📝 网申助手」")
        st.info("**怎么确认装好了（最省事的办法）**：装完脚本后**刷新本页**，如果右下角多出一个蓝色的 "
                "「📝 网申助手」小胶囊 —— 说明脚本已经在运行了。\n\n"
                "看不到胶囊 → ① 油猴是否已启用该脚本；② 拖入 .user.js 时是否点了「安装」；"
                "③ 打开桌面 `简历\\脚本自检.html` 按里面的步骤排查（那里还有一张假网申表可以练手）。")
        if st.button("⬇️ 生成/更新 网申助手.user.js"):
            from ihub import autofill
            path = autofill.save_userscript(prof=prof_mod.load())
            st.success(f"已生成：{path}（资料更新后重新点一次即可）")

    # ============ 📮 网申跟踪 ============
    with tab6:
        st.markdown("#### 📮 网申跟踪（我投了哪些、进行到哪一步）")
        st.caption("秋招/实习都能记：公司、岗位、城市、截止日期、进度、备注。进度变化会自动记录投递日期。")
        stt = db.app_stats()
        c = st.columns(6)
        for i, s in enumerate(db.STAGES):
            c[i].metric(s, stt.get(s, 0))

        # ---- 重复投递检查（烟草等"同批次只能报一个岗"的单位，重复投=直接取消资格）----
        _idx = _applied_index()
        _dups = {k: v for k, v in _idx.items() if len(v) > 1}
        _job_dups = []
        for _j in db.query(apply_state=1, active_only=False, limit=500):
            _h = _dup_hits(_j.get("company"), _j.get("title"), _idx)
            if _h:
                _job_dups.append((_j, _h))
        if _dups or _job_dups:
            st.error(f"⚠️ 发现 {len(_dups) + len(_job_dups)} 处疑似重复投递 —— "
                     "烟草明确「同一批次只能报 1 个单位 1 个岗位，重复投递取消资格」，投前务必核对。")
            with st.expander("查看重复明细", expanded=True):
                for (kc, kt), rows in _dups.items():
                    st.markdown(f'**{kc}｜{kt}**　→ 已有 {len(rows)} 条记录（进度：'
                                + "、".join(str(r.get("stage")) for r in rows) + "）")
                for _j, _h in _job_dups:
                    st.markdown(f'**投递箱里的「{_j.get("company")}｜{_j.get("title")}」**　→ 你已投过：'
                                + "、".join(f'{r.get("company")}｜{r.get("title")}（{r.get("stage")}）'
                                            for r in _h[:3]))
        else:
            st.caption("✅ 没有发现重复投递。每次投完记得把这里的「进度」改成「已投」。")

        with st.expander("➕ 手动添加一条（官网/公众号看到的岗位）"):
            with st.form("add_app", clear_on_submit=True):
                a1, a2, a3 = st.columns(3)
                comp = a1.text_input("公司")
                tit = a2.text_input("岗位")
                cty = a3.text_input("城市", value=f_city if f_city != "全部" else "潍坊")
                a4, a5, a6 = st.columns(3)
                url = a4.text_input("网申/公告链接")
                dl2 = a5.text_input("截止日期（YYYY-MM-DD）")
                jt = a6.selectbox("类型", ["秋招", "实习"])
                note0 = st.text_input("备注")
                if st.form_submit_button("添加"):
                    db.app_add(comp, tit, cty, url, jt, dl2, note0)
                    st.success("已添加")
                    st.rerun()

        if st.button("⬇️ 把「投递箱」里的岗位加入跟踪"):
            ids = [r["id"] for r in db.query(apply_state=1, limit=500)]
            n = db.app_add_from_job_ids(ids) if ids else 0
            st.success(f"已加入 {n} 条（重复的自动跳过）")

        rows_app = db.app_list(limit=800)
        if not rows_app:
            st.info("还没有跟踪记录：先把岗位加入投递箱，或手动添加一条。")
        else:
            edf = pd.DataFrame(rows_app)
            edf["截止日期"] = edf["deadline"].fillna("")
            edf["投递日期"] = edf["applied_at"].fillna("")
            edf["进度"] = edf["stage"]
            edit_app = st.data_editor(
                edf[["id", "company", "title", "city", "进度", "投递日期", "截止日期", "url", "note"]],
                hide_index=True,
                disabled=["id", "company", "title", "city", "投递日期", "url"],
                column_config={
                    "id": None,
                    "company": "公司", "title": "岗位", "city": "城市",
                    "进度": st.column_config.SelectboxColumn("进度", options=db.STAGES),
                    "投递日期": "投递日期", "截止日期": "截止日期",
                    "url": st.column_config.LinkColumn("网申/公告链接"),
                    "note": st.column_config.TextColumn("备注", width="medium"),
                },
                num_rows="fixed", width="stretch", height=460,
            )
            b1, b2, b3 = st.columns([1, 1, 3])
            if b1.button("💾 保存进度", type="primary"):
                for r in edit_app.itertuples():
                    db.app_update(int(r.id), stage=r.进度, deadline=r.截止日期, note=r.note)
                st.success("已保存")
                st.rerun()
            if b2.button("📤 导出网申清单 CSV"):
                p = os.path.join(OUT_DIR, f"网申跟踪_{datetime.date.today().isoformat()}.csv")
                os.makedirs(OUT_DIR, exist_ok=True)
                pd.DataFrame(rows_app).to_csv(p, index=False, encoding="utf-8-sig")
                st.success(f"已导出：{p}")
            del_id = b3.number_input("删除某条（填 id）", 0, 10**9, 0, 1)
            if b3.button("🗑 删除") and del_id:
                db.app_delete(int(del_id))
                st.rerun()

    # ============ 🛰 秋招渠道 ============
    with tab7:
        st.markdown("#### 🛰 秋招渠道与岗位（找全 + 直达官方报名）")
        from ihub import campus_channels as cc

        st.markdown("**① 秋招岗位库**（本工具已收录的秋招岗位，含官方报名入口）")
        cq1, cq2 = st.columns([1, 1])
        qcity = cq1.selectbox("城市", ["全部", "潍坊", "昆明", "大理", "全国"], key="cq_city")
        qkw = cq2.text_input("关键词（公司/岗位，可空）", key="cq_kw")
        q_rows = db.query(city=None if qcity == "全部" else qcity,
                          keyword=qkw or None, job_type="秋招",
                          active_only=False, limit=500)
        if not q_rows:
            st.info("秋招岗位库暂无数据：可在「📚 备考方案」上方用“导入秋招 CSV”或用下面渠道自己找（找到后可按模板导入）。")
        else:
            import pandas as _pd
            qdf = _pd.DataFrame(q_rows)
            qdf["报名入口"] = qdf["official_url"].fillna("").where(qdf["official_url"].fillna("") != "", qdf["link"])
            qdf["截止"] = qdf["deadline"].fillna("")
            st.dataframe(
                qdf[["company", "title", "city", "batch", "degree", "截止", "报名入口", "source"]],
                hide_index=True,
                column_config={
                    "company": "单位", "title": "岗位", "city": "城市", "batch": "届别",
                    "degree": "学历", "截止": "截止日期",
                    "报名入口": st.column_config.LinkColumn("官方报名/公告"),
                    "source": "来源",
                },
                width="stretch", height=320,
            )
            if st.button("⬇️ 把上面这些秋招岗位加入「📮 网申跟踪」"):
                n = db.app_add_from_job_ids([r["id"] for r in q_rows])
                st.success(f"已加入 {n} 条（重复自动跳过），去「📮 网申跟踪」维护进度")

        st.divider()
        st.markdown("**② 一键搜索直达**（把城市/关键词组合，直接跳到各平台的秋招结果页）")
        s1, s2 = st.columns([1, 2])
        scity = s1.selectbox("搜索城市", ["潍坊", "昆明", "大理", "全国", "山东", "云南"], key="srch_city")
        skw = s2.text_input("搜索关键词（专业方向/岗位，如 物联网、电气、信息科技）", value="物联网", key="srch_kw")
        links = cc.search_links(city="" if scity == "全国" else scity, keyword=skw)
        cols = st.columns(3)
        for i, (name, url) in enumerate(links):
            cols[i % 3].markdown(f"- [{name}]({url})")

        st.divider()
        st.markdown("**③ 七大渠道官方入口**（点开即到官方/公开页面）")
        for title, items in cc.CHANNEL_GROUPS:
            with st.expander(title, expanded=False):
                c = st.columns(2)
                for i, (name, url) in enumerate(items):
                    c[i % 2].markdown(f"- [{name}]({url})")
        st.caption("提示：BOSS/智联/牛客等需登录后查看；本页只提供官方入口与搜索直达，不代替登录抓取。")

    # ============ 📚 备考方案 ============
    with tab8:
        # ---- 成品方案：云南烟草备考作战方案（完整版，可直接打印）----
        _plan_md = os.path.join(ROOT_APP, "备考冲刺资料", "云南烟草2027届备考作战方案.md")
        _plan_docx = os.path.join(ROOT_APP, "备考冲刺资料", "云南烟草2027届备考作战方案.docx")
        if os.path.exists(_plan_md):
            with st.expander("🍃 云南烟草 2027 届 · 备考作战方案（完整版，先看这个）", expanded=True):
                st.caption("两家招录主体的差异与「报哪个更划算」　|　2027 届时间轴（含网申窗口）　|　"
                           "分值目标与战略放弃　|　行测五模块策略　|　专业科目（按你的专业定向）　|　"
                           "公基必背清单　|　9.17 起逐日作战表　|　网申材料与避坑（重复投递=取消资格）　|　"
                           "面试题库 + STAR 故事　|　题库与网课清单")
                _pc1, _pc2 = st.columns(2)
                _download_file(_plan_docx, "⬇ 下载 Word（.docx，可打印）",
                               "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                               container=_pc1)
                _download_file(_plan_md, "⬇ 下载 Markdown（.md）", "text/markdown",
                               container=_pc2)
                with st.container(height=430):
                    st.markdown(open(_plan_md, encoding="utf-8").read())
            st.divider()

        st.markdown("#### 📚 备考方案（选目标岗位 → 自动出方案）")
        from ihub import study
        tname = st.selectbox("我要备考的目标", list(study.TARGETS.keys()), key="study_target")
        d = study.TARGETS[tname]
        st.info(d["note"])
        st.markdown("**考什么**：" + "　".join(f"`{s}`" for s in d["subjects"]))

        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("**🎬 看什么课**")
            for name, url in d["courses"]:
                st.markdown(f"- [{name}]({url})")
        with c2:
            st.markdown("**✍️ 哪里刷题**")
            for name, url in list(d["practice"]) + list(study.COMMON_PRACTICE):
                st.markdown(f"- [{name}]({url})")
        with c3:
            st.markdown("**🔗 官方信息源**")
            for name, url in list(d["official"]) + list(study.COMMON_OFFICIAL):
                st.markdown(f"- [{name}]({url})")

        st.markdown("**🗓 复习时间表**")
        import pandas as _pd2
        st.dataframe(_pd2.DataFrame(study.TIME_PLAN, columns=["阶段", "做什么"]),
                     hide_index=True, width="stretch")

        st.markdown("**💬 面试准备**")
        for it in study.INTERVIEW:
            st.markdown(f"- {it}")

        st.divider()
        st.markdown("**✅ 打卡（本地保存，按目标分别记录）**")
        checks = study.load_checks()
        cur = dict(checks.get(tname, {}))
        changed = False
        for i, it in enumerate(study.CHECK_ITEMS):
            v = st.checkbox(it, value=bool(cur.get(str(i), False)), key=f"chk_{tname}_{i}")
            if v != bool(cur.get(str(i), False)):
                cur[str(i)] = v
                changed = True
        if changed:
            checks[tname] = cur
            study.save_checks(checks)
            st.caption("已保存进度 ✅")

        st.divider()
        st.markdown("**➕ 导入新的秋招岗位（自己找到的公告 / 采集助手导出的 CSV 都行）**")
        st.caption("CSV 表头（缺列也不影响）：岗位,公司,城市,学历,标签,链接,截止日期,描述,岗位类型(填“秋招”),届别,来源")
        st.caption("支持 Excel 另存的 CSV、飞书多维表格「下载为 CSV」、以及采集助手/采集书签导出的文件；"
                   "表头写「职位名称/单位名称/工作城市/薪资待遇」这类变体也能自动认出来。")
        upl = st.file_uploader("上传秋招 CSV（采集助手导出的文件直接传这里）", type=["csv"], key="csv_qiu")
        if upl is not None:
            txt = upl.read().decode("utf-8-sig", "ignore")
            from ihub import importer as _imp
            stt = _imp.import_csv_text(txt, source="采集导入")
            for w in stt.get("warnings") or []:
                st.info(f"提醒：{w}")
            if stt["rows"]:
                st.success(f"已导入 {stt['rows']} 行 → 新增 {stt['inserted']} / 更新 {stt['updated']}"
                           f"（识别到的列：{'、'.join(stt['mapping'].keys())}）")
            else:
                st.warning("没识别到「岗位」列：请确认表头含“岗位/职位/岗位名称”等列名（第一列会被兜底当作岗位名）")

        st.markdown("**📋 直接粘贴导入（没导出权限时用这个）**")
        st.caption("在飞书多维表格 / Excel / WPS 里**选中表格区域 → Ctrl+C → 粘到下面 → 点导入**。"
                   "复制出来的是制表符分隔，同样能自动认列名。（飞书表格若禁用了导出，这招照样能用）")
        paste = st.text_area(
            "把表格内容粘到这里（含表头那一行）", height=170, key="paste_tbl",
            placeholder="岗位名称\t公司\t工作城市\t投递链接\n数据分析工程师\t云南机场集团\t昆明\thttps://...")
        if st.button("📥 导入粘贴的内容", key="paste_import"):
            if not paste or not paste.strip():
                st.warning("先粘贴表格内容再点导入。")
            else:
                from ihub import importer as _imp2
                stt2 = _imp2.import_csv_text(paste, source="粘贴导入")
                for w in stt2.get("warnings") or []:
                    st.info(f"提醒：{w}")
                if stt2["rows"]:
                    st.success(f"已导入 {stt2['rows']} 行 → 新增 {stt2['inserted']} / 更新 {stt2['updated']}"
                               f"（分隔符：{'制表符' if stt2.get('delimiter') == chr(9) else stt2.get('delimiter')}，"
                               f"识别到的列：{'、'.join(stt2['mapping'].keys())}）")
                    st.rerun()
                else:
                    st.warning("没解析出数据行：确认第一行是表头（列名如 岗位/公司/城市/链接），后面每行一条。")

    # ============ 简历定制（粘贴 JD → 定向简历 + 网申文案） ============
    with tab9:
        from ihub import tailor as _tk
        st.markdown("#### 📝 简历定制与网申文案")
        st.caption("粘贴岗位 JD → 自动识别岗位方向 → 生成对应侧重的简历（docx / pdf）"
                   "与网申各栏文案。全部在本机完成，不联网、不上传。")

        with st.expander("🧰 配套工具下载（投递工作台 / 网申助手 / 速填卡 / 成品简历）"):
            st.caption("投递工作台：单个 HTML 文件，双击就能用（粘贴 JD 出定向简历 + 批量广投清单）。"
                       "网申助手：装到浏览器后，在网申页面一键填表。")
            _tools = [
                (os.path.join(ROOT_APP, "简历材料", "05_投递工作台.html"), "⬇ 投递工作台.html", "text/html"),
                (os.path.join(ROOT_APP, "简历材料", "04_网申速填卡.txt"), "⬇ 网申速填卡.txt", "text/plain"),
                (os.path.join(ROOT_APP, "网申助手.user.js"), "⬇ 网申助手.user.js", "text/javascript"),
                (os.path.join(ROOT_APP, "网申书签.txt"), "⬇ 网申书签.txt（免装扩展）", "text/plain"),
                (os.path.join(ROOT_APP, "简历材料", "02_万能通用版_罗广睿_中国民航大学.pdf"),
                 "⬇ 万能通用版简历.pdf", "application/pdf"),
                (os.path.join(ROOT_APP, "简历材料", "02_万能通用版_罗广睿_中国民航大学.docx"),
                 "⬇ 万能通用版简历.docx",
                 "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
            ]
            _cols = st.columns(3)
            for _i, (_p, _lb, _mime) in enumerate(_tools):
                with _cols[_i % 3]:
                    _download_file(_p, _lb, _mime)
            st.caption("改完资料想重新生成整套材料：`venv\\Scripts\\python.exe gen_resume_kit.py`")

        st.divider()
        _box = db.query(apply_state=1, active_only=False, limit=200)
        _pick_opts = ["（不用，下面手动填）"] + [
            f'{r.get("company") or "（无公司名）"}｜{r.get("title") or ""}' for r in _box]
        _pick = st.selectbox("① 从投递箱带一条（选填）", _pick_opts, key="tk_pick")

        _c1, _c2 = st.columns(2)
        _company = _c1.text_input("公司名称（选填，会写进简历的求职意向）", key="tk_co")
        _jobtitle = _c2.text_input("岗位名称（选填）", key="tk_jt")
        if _pick != _pick_opts[0]:
            _co, _, _jt = _pick.partition("｜")
            _company = _company or _co.strip()
            _jobtitle = _jobtitle or _jt.strip()

        _jd = st.text_area("② 岗位 JD / 任职要求（整段粘贴，越全越准）", height=170, key="tk_jd")

        if not (_jd.strip() or _jobtitle.strip()):
            st.info("把岗位 JD 或岗位名称填进来，下面就会出现「方向识别 → 匹配度 → 定向简历 → 网申文案」。")
        else:
            _det, _scores, _weak = _tk.detect(_jd, _jobtitle)
            st.markdown("##### ③ 岗位方向")
            _labels = ["🤖 智能识别 → " + _tk.label_of(_det)] + [_tk.label_of(k) for k in _tk.ORDER] + ["🧩 万能通用版"]
            _keys = [_det] + list(_tk.ORDER) + ["universal"]
            _idx = st.radio("识别错了就点正确的那一个", range(len(_labels)),
                            format_func=lambda i: _labels[i], horizontal=True, key="tk_dir")
            _key = _keys[_idx]
            _ctx = {"company": _company, "title": _jobtitle}
            if _weak:
                st.caption("JD 里技术关键词不多，已默认按技术向处理；可手动改。")

            _an = _tk.analyze(_jd + " " + _jobtitle, _key)
            _m1, _m2 = st.columns([1, 4])
            with _m1:
                st.metric("匹配度", f'{_an["score"]} 分', help="综合 JD 关键词覆盖率与该方向核心词命中率估算")
            with _m2:
                st.caption("✅ 简历里已覆盖：" + ("、".join(_an["hit"]) or "—"))
                if _an["miss"]:
                    st.caption("⚠️ JD 提到、简历未体现（面试会被追问，**不要硬编**）："
                               + "、".join(_an["miss"][:15]))

            st.markdown("##### ④ 定向简历")
            if st.button("🛠 生成这份岗位的定向简历", type="primary", key="tk_gen"):
                _stem = (str(_company) + "_" + str(_jobtitle)).strip("_") or _tk.file_of(_key)
                _stem = re.sub(r'[\\/:*?"<>|\s]+', "_", _stem)[:50]
                os.makedirs(OUT_DIR, exist_ok=True)
                _dpath = os.path.join(OUT_DIR, f"{_stem}_简历.docx")
                _ppath = os.path.join(OUT_DIR, f"{_stem}_简历.pdf")
                _tk.resume_docx(_key, _dpath, _ctx)
                try:
                    _tk.build_pdf(_key, _ppath, _ctx)
                except Exception as _e:                     # 缺 reportlab / 字体时降级
                    _ppath = None
                    st.warning(f"PDF 未生成（{_e}）——docx 已就绪，可直接上传或用 Word 另存为 PDF。")
                st.session_state["tk_made"] = {"docx": _dpath, "pdf": _ppath, "key": _key}

            _made = st.session_state.get("tk_made")
            if _made and _made.get("key") == _key:
                st.success(f"已生成：{os.path.relpath(_made['docx'], ROOT_APP)}")
                _d1, _d2 = st.columns(2)
                _download_file(_made["docx"], "⬇ 下载 Word（.docx）",
                               "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                               container=_d1)
                if _made.get("pdf"):
                    _download_file(_made["pdf"], "⬇ 下载 PDF（上传网申用）", "application/pdf",
                                   container=_d2)
            else:
                st.caption("生成的文件会放到 投递文件/ 文件夹，同时在这里给出下载按钮。")

            st.markdown("##### ⑤ 网申填写文案")
            st.caption("点每块右上角的复制图标 → 直接粘进网申表单对应的框。")
            _pack = _tk.fill_pack(_key, _ctx)
            _short = [x for x in _pack if len(x[1]) < 60]
            _long = [x for x in _pack if len(x[1]) >= 60]
            _pcols = st.columns(2)
            for _i, (_lb, _txt) in enumerate(_short):
                with _pcols[_i % 2]:
                    st.caption(_lb)
                    st.code(_txt or "（未填）", language=None)
            for _lb, _txt in _long:
                with st.expander(f"📋 {_lb}"):
                    st.code(_txt, language=None)

            _all_txt = "\n\n".join(f"【{_lb}】\n{_txt}" for _lb, _txt in _pack)
            st.download_button("⬇ 下载本岗位全部文案（txt）", data=_all_txt.encode("utf-8"),
                               file_name=f"网申文案_{_tk.file_of(_key)}.txt", mime="text/plain",
                               key="tk_dl_all")

    # ============ 🌏 云南秋招（昆明 / 大理 投递渠道地图） ============
    with tab10:
        from ihub import yunnan as yn
        from ihub import platforms as P

        st.markdown("#### 🌏 云南秋招投递渠道地图（昆明 / 大理）")
        st.caption("通用平台抓不到的（要登录、动态渲染、只走公众号）这里用「渠道地图」兜住："
                   "每个单位一条，给官方公告页 / 网申入口 / 搜索直达。链接会变，但「去哪找」不会变。")
        st.info("**你的定位**：2027 届 · 昆明 + 大理 · 央国企为主 · 不限企业类型 · 重点备考烟草。"
                "下面按「与你专业的契合度」排了序，★★★★ 以上的就是最该投的。")

        # ────────────── 全网平台入口（BOSS / 智联 / 牛客 / 国聘 / 24365 …）──────────────
        st.markdown("##### 🌐 全网平台入口（点一下就直接跳到该平台去搜）")
        st.caption("实测结论：BOSS直聘、智联、前程无忧、猎聘、牛客、国聘网、24365、高校人才网 "
                   "**全是前端渲染**，静态爬虫拿不到岗位（硬爬违反 robots、随时失效）。"
                   "所以这里给的是【搜索直达】：点开＝在该平台内搜「昆明/大理 + 你的专业 + 应届」，"
                   "绕开登录墙，永远不会 404。")

        with st.expander("🗓 今天该干什么（6 步，照做就不漏公告）", expanded=True):
            for _i, (_step, _task, _url) in enumerate(P.today_plan(), 1):
                _c1, _c2 = st.columns([5, 1])
                _c1.markdown(f"**{_step}**　{_task}")
                if _url:
                    _c2.link_button("打开", _url, key=f"tp_{_i}")

        _JOB_KW = ("嵌入式", "物联网", "自动化", "电子信息", "通信", "运维", "测试")
        with st.expander("🔍 搜索关键词（在每个平台都用这一套，轮着搜）", expanded=False):
            st.markdown("**专业词**：" + "　".join(f"`{k}`" for k in _JOB_KW) +
                        "　`应届生`　`校招`　`2027届`")
            st.markdown("**云南行业词**：`烟草`　`中烟`　`电网`　`机场`　`空管`　`地铁`　`国企`　`事业单位`")
            st.caption("同一个平台换几个词搜，结果差别很大 —— 只搜一个词会漏掉一半岗位。")

        for _cat, _items in P.cats_in_order():
            with st.expander(f"{_cat}（{len(_items)} 个）", expanded=("云南本地" in _cat)):
                for _j, _p in enumerate(_items):
                    _badge = "需登录" if _p["login"] else "免登录"
                    st.markdown(f'**{_p["name"]}**　<small>· {_badge} · {_p["crawl"]}</small>',
                                unsafe_allow_html=True)
                    st.caption("适配：" + _p["fit"])
                    st.caption("怎么筛：" + _p["how"])
                    if _p["tip"]:
                        st.caption("提醒：" + _p["tip"])
                    _b = st.columns([1, 1, 1])
                    _b[0].link_button("🔗 打开官网", _p["url"], key=f"pl_u_{_cat[:2]}_{_j}")
                    _b[1].link_button("🔍 搜云南应届岗",
                                      P.bd_site(_p["domain"], "昆明 大理 招聘 应届"),
                                      key=f"pl_s_{_cat[:2]}_{_j}")
                    _b[2].link_button("💬 微信搜公告", P.wx("云南 国企 招聘 2027 应届"),
                                      key=f"pl_w_{_cat[:2]}_{_j}")
                    st.markdown("")

        with st.expander("🔗 全部搜索直达链接（一键复制，也能存到手机）", expanded=False):
            st.code(P.links_text(), language=None)

        _pd1, _pd2 = st.columns([1, 3])
        _pd1.download_button("⬇ 下载平台矩阵（txt）", data=P.as_text().encode("utf-8"),
                             file_name="全网招聘平台矩阵.txt", mime="text/plain", key="pl_dl")
        _pd2.caption("20+ 个正规平台（国家级官方 / 综合招聘 / 校招垂直 / 云南本地高校）。"
                     "凡是要你先交钱的「内推 · 保offer」一律是骗子。")

        st.divider()

        y1, y2, y3 = st.columns([1, 1, 2])
        with y1:
            st.download_button("⬇ 导出渠道地图（txt）", data=yn.as_text().encode("utf-8"),
                               file_name="云南秋招投递渠道地图.txt", mime="text/plain",
                               key="yn_dl")
        with y2:
            if st.button("📋 复制全部到剪贴板提示", key="yn_copy"):
                st.success("已生成，点上面的 txt 下载即可（手机备忘录也能看）")
        with y3:
            st.caption("标「官方直达」的是核对过的；其余给搜索直达 —— 永远不会 404。")

        st.divider()
        st.markdown("##### 🎯 先看这些（★★★☆ 以上，按契合度排序）")
        for u in yn.for_me():
            with st.expander(f'{u["heat"]}　{u["name"]}　—　{u["fit"][:34]}…'):
                cols = st.columns([3, 1])
                with cols[0]:
                    if u.get("portal"):
                        st.markdown(f'**官方公告**：{u["portal"]}')
                    if u.get("apply"):
                        st.markdown(f'**网申入口**：{u["apply"]}')
                    if u.get("apply_note"):
                        st.caption("说明：" + u["apply_note"])
                    st.markdown(f'**搜索直达**：{u["search"]}')
                    st.markdown(f'**对口岗位**：{u["fit"]}')
                    st.markdown(f'**招聘节奏**：{u["rhythm"]}')
                    st.warning(u["tips"])
                with cols[1]:
                    if st.button("➕ 记进网申跟踪", key="yn_add_" + str(abs(hash(u["name"])) % 10 ** 8)):
                        db.app_add(company=u["name"], title="（岗位待定，公告发布后填）",
                                   city="昆明/大理", url=u.get("apply") or u.get("portal") or u["search"],
                                   job_type="秋招", deadline="", note=u["fit"])
                        st.success("已加入「📮 网申跟踪」")
                        st.rerun()

        st.divider()
        st.markdown("##### 📚 全部单位（按类别）")
        for cat, items in yn.cats_in_order():
            with st.expander(f"{cat}（{len(items)} 家）", expanded=False):
                for u in items:
                    st.markdown(f'**{u["heat"]}　{u["name"]}**')
                    bits = []
                    if u.get("portal"):
                        bits.append(f'[官方公告]({u["portal"]})')
                    if u.get("apply"):
                        bits.append(f'[网申入口]({u["apply"]})')
                    bits.append(f'[搜索直达]({u["search"]})')
                    st.markdown("　|　".join(bits))
                    st.caption(f'对口：{u["fit"]}　·　节奏：{u["rhythm"]}')
                    st.caption("💡 " + u["tips"])
                    st.markdown("")

        st.divider()
        st.markdown("##### 🗓 每周固定动作（照做就不漏公告）")
        wdf = pd.DataFrame(yn.WEEKLY, columns=["时间", "动作", "入口"])
        st.dataframe(wdf, hide_index=True, width="stretch",
                     column_config={"入口": st.column_config.LinkColumn("入口")})
        st.caption("⚠️ 烟草「同一批次只能报 1 个单位 1 个岗位，重复投递取消资格」——"
                   "投之前先在「📮 网申跟踪」记一笔，投完立刻改状态。")

    # ============ 🍃 烟草监控（主力备考方向，单独一页） ============
    with tab11:
        from ihub import tobacco as TB

        st.markdown("#### 🍃 烟草招聘监控 —— 只盯报名窗口，不让你错过任何一个批次")
        st.caption("监控源头：**国家烟草专卖局「人才招聘专栏」**（全国各省局、各中烟的公告都在这首发，"
                   "云南中烟/云南省局的公告同样会出现在这里）。点一下按钮扫一遍，**只有新增才报给你**。")
        st.warning("烟草铁律：**同一批次只能报 1 个单位 1 个岗位，重复投递直接取消资格**；"
                   "网申窗口通常只有 **7~10 天**（实测公告原文「逾期不再受理」）。看到公告当天就要动手，"
                   "投前先在「📮 网申跟踪」记一笔。")

        with st.expander("🎯 烟草岗位怎么选（合适 / 轻松 / 钱多 —— 权重可自己调）", expanded=False):
            from ihub import tobacco_roles as TR
            st.caption("烟草公告的岗位表动辄几十类。这里按你要的三个维度打分（1~5★），"
                       "**拖滑条改权重，排序立刻变** —— 但结论其实很稳：技术岗通吃，一线岗垫底。")
            _w1, _w2, _w3 = st.columns(3)
            _wf = _w1.slider("合适（专业对口）", 0.0, 1.0, 0.40, 0.05, key="tr_wf")
            _wl = _w2.slider("轻松（强度低）", 0.0, 1.0, 0.30, 0.05, key="tr_wl")
            _wp = _w3.slider("钱多", 0.0, 1.0, 0.30, 0.05, key="tr_wp")
            st.success(TR.summary_text(_wf, _wl, _wp))
            _rk = TR.ranked(_wf, _wl, _wp)
            st.dataframe(
                pd.DataFrame([{
                    "排名": i,
                    "岗位类别": r["name"],
                    "总分": r["score"],
                    "合适": TR.stars(r["fit"]),
                    "轻松": TR.stars(r["light"]),
                    "钱多": TR.stars(r["pay"]),
                    "干什么": r["duty"][:34],
                } for i, r in enumerate(_rk, 1)]),
                hide_index=True, width="stretch")
            for _i, _r in enumerate(_rk[:3], 1):
                st.markdown(f'**{_i}. {_r["name"]}**（{_r["score"]} 分）'
                            f'　合适{TR.stars(_r["fit"])} 轻松{TR.stars(_r["light"])} '
                            f'钱多{TR.stars(_r["pay"])}')
                st.caption(f'干什么：{_r["duty"]}')
                st.caption(f'云南情况：{_r["yunnan"]}')
                st.caption(f'⚠️ 坑：{_r["trap"]}')
            with st.expander("看全部 9 类的详细说明 / 导出", expanded=False):
                st.markdown(TR.as_text(_wf, _wl, _wp))
            st.download_button("⬇ 下载岗位推荐表（txt）",
                               data=TR.as_text(_wf, _wl, _wp).encode("utf-8"),
                               file_name="烟草岗位推荐_合适轻松钱多.txt",
                               mime="text/plain", key="tr_dl")
            st.caption("⚠️ 分数是按公开信息与行业普遍情况整理的**参考值，不是官方数据**；"
                       "各类别各省叫法不同（信息化类/计算机类），以当年公告岗位表为准，"
                       "报名前务必核对专业目录要求。")

        st.info("**你的取向**：偏技术、不要一线操作岗；**昆明和大理都投**。"
                "下面的岗位取向标记就是按这个规则自动判的（✅技术/管理类 加分，⛔一线/操作类 降级）。")
        _seen = TB.load_seen()
        _c1, _c2, _c3 = st.columns([1, 1, 2])
        _deep = _c1.checkbox("顺便抓报名窗口", value=True, key="tb_detail",
                             help="对新公告抓详情页，提取「报名时间 / 报名平台 / 是否限制报考岗位数」，稍慢几秒")
        _tech = _c1.checkbox("只看技术/管理类", value=True, key="tb_tech",
                             help="勾上＝把一线操作岗（生产操作类/车间/烟叶收购…）从「新增」里滤掉，"
                                  "它们仍会留在下面的全部公告表里")
        if _c2.button("🔍 立即扫描一次", type="primary", key="tb_scan"):
            with st.spinner("正在扫描国家烟草专卖局招聘专栏…"):
                try:
                    st.session_state["tb_res"] = TB.scan(
                        pages=2, detail_top=8 if _deep else 0, tech_only=_tech)
                except Exception as e:
                    st.error(f"扫描失败：{e}")
        _c3.caption(f"已累计记录 {len(_seen)} 条历史公告（用于算「新增」）。"
                    f"第一次扫会报出全部历史公告，属正常；之后只报增量。")

        _res = st.session_state.get("tb_res")
        if not _res:
            st.info("点上面的「🔍 立即扫描一次」开始。系统已配置**每天自动扫描**（早 8:30 / 晚 20:30），"
                    "有新增会在对话里直接推给你。")
        else:
            _new = TB.by_priority(_res["new"])
            _urgent = TB.urgent(TB.by_priority(_res["all"]))
            m1, m2, m3 = st.columns(3)
            m1.metric("本轮新增", f'{len(_new)} 条')
            m2.metric("累计已见", f'{_res["total_seen"]} 条')
            m3.metric("10 天内截止", f'{len(_urgent)} 条')
            st.caption(f'扫描时间：{_res["checked_at"]}')

            if _urgent:
                st.error("⏰ **正在报名、且 10 天内截止**（这类必须马上投）：")
                for it in _urgent:
                    st.markdown(f'**[{it["days_left"]} 天] {it["title"]}**　{it["link"]}')

            if not _new:
                st.success("✅ 本轮没有新增公告。")
            else:
                st.markdown(f"##### 🆕 本轮新增 {len(_new)} 条")
            for _i, it in enumerate(_new):
                _role = it.get("role") or ""
                with st.expander(f'{TB.stars(it["priority"])}　{_role}　[{it["kind"]}]　{it["title"][:42]}'):
                    st.markdown(f'**公告原文**：{it["link"]}')
                    if _role:
                        st.markdown(f'**岗位取向**：{_role}　{it.get("role_note", "")}')
                    if it.get("published"):
                        st.caption(f'发布月份：{it["published"]}　性质：{it["kind"]}　'
                                   f'优先级：{TB.stars(it["priority"])}')
                    if it.get("apply_from") or it.get("apply_to"):
                        _win = (f'报名窗口：{it.get("apply_from") or "?"} ~ '
                                f'{it.get("apply_to") or "?"}（{it.get("open_days") or "?"} 天）')
                        if it.get("days_left") is not None:
                            _d = it["days_left"]
                            _win += "　⏰ 还剩 %d 天" % _d if _d >= 0 else "　（已结束）"
                        st.info(_win)
                    if it.get("apply_platform"):
                        st.markdown(f'**报名平台**：{it["apply_platform"]}　'
                                    f'（点开后用右下角「📝 网申助手」填）')
                    if it.get("quota_note"):
                        st.warning(it["quota_note"])
                    _b1, _b2 = st.columns([1, 1])
                    if _b1.button("➕ 记进网申跟踪", key=f'tb_add_{_i}_{it["id"]}'):
                        db.app_add(company=it["title"][:24], title="（报名后补岗位）",
                                   city="云南" if it.get("is_yunnan") else "",
                                   url=it.get("apply_platform") or it["link"],
                                   job_type="秋招", deadline=it.get("apply_to") or "",
                                   note=it["title"])
                        st.success("已加入「📮 网申跟踪」，投完记得标记已投。")
                        st.rerun()
                    _b2.markdown(f'[打开公告原文 ↗]({it["link"]})')

            st.divider()
            st.markdown("##### 📋 全部公告（按优先级排序，报名中的排最前）")
            _tb_rows = []
            for it in TB.by_priority(_res["all"]):
                _tb_rows.append({
                    "优先级": TB.stars(it["priority"]),
                    "岗位": it.get("role") or "·",
                    "性质": it["kind"],
                    "公告": it["title"][:60],
                    "发布": it.get("published") or "—",
                    "链接": it["link"],
                    "本轮新增": "🆕" if it.get("is_new") else "",
                })
            st.dataframe(pd.DataFrame(_tb_rows), hide_index=True, width="stretch",
                         column_config={"链接": st.column_config.LinkColumn("公告原文")})

            st.download_button("⬇ 导出监控报告（txt）", data=TB.as_text(_res).encode("utf-8"),
                               file_name="烟草监控报告.txt", mime="text/plain", key="tb_dl")

        st.divider()
        with st.expander("📌 这个监控盯得住 / 盯不住什么（说清楚，别误判）"):
            st.markdown(
                "- **盯得住**：国家烟草专卖局「人才招聘专栏」的**全部公告**（各省局、各中烟、专业公司），"
                "以及本地数据源里标题含烟草的条目（高校就业网、人社厅、应届生求职网等）。\n"
                "- **盯不住**：云南中烟、云南省局官网是 Vue 前端渲染，静态抓不到 —— 但它们发的公告"
                "**同样会出现在国家局专栏**，所以不影响你不漏公告。\n"
                "- **建议**：每天早晚各跑一次（自动化已配好），公告一出当天就能看到；"
                "国家局专栏还有「招聘」热搜词入口，可配合人工扫一眼。\n"
                "- 报名系统多为第三方平台（如 `qhtobacco.zhaopin.com`），点报名平台进官网后，"
                "**右下角「📝 网申助手」照样能帮你填**。")

    # ============ 说明 ============

    with tab12:
        st.markdown("#### 使用说明")
        st.markdown(
            "1. 抓取 → 筛选 → 勾选 🎯投递箱 → 保存；\n"
            "2. 「投递工作台」逐条生成**投递理由**与**按岗位定制简历**(docx 输出到 投递文件/ 文件夹)，\n"
            "3. 点**原平台链接**投递，或到**企业官网招聘**页核验后再投，完成后标记“已投”；\n"
            "4. 自动更新：`python scheduler.py --hours 6`；其他来源可 CSV 导入：`python run_import.py 表.csv`。")
        st.markdown("#### 🛰 信息渠道说明（企业官网 + 更多来源）")
        st.markdown(
            "- **两列链接的含义**：`投递（原平台）`= 实习僧原始详情页（招聘方在用的申请入口）；`企业官网招聘`= 公司官方招聘入口，用于**核验与官网直达**；\n"
            "- 内置已核验的官网入口目前含：字节跳动、蔚来（持续补充）。其余为空属正常，可自行添加：编辑 `data/official_urls.json`（文件不存在则新建），格式：`{\"公司名\": \"https://官网招聘地址\"}`，重开页面即生效；\n"
            "- **更多自动渠道**：① 实习僧（当前）；② `RSS订阅`：站点官方提供 RSS/Atom 时可接入（在 `ihub/config.py` 的 `RSS_FEEDS` 添加地址）；③ `CSV导入`：官网/群文件/Excel 整理的清单直接导入；\n"
            "- BOSS直聘/智联/牛客等大平台需登录+强反爬，为避免封号与违规未自动接入，建议到官网或通过其官方 App 使用。")
        st.markdown("#### 🏢 就业平台官方入口（登录后自用，含政府/官方渠道）")
        st.markdown(
            "下列平台**岗位列表与投递都需本人登录**（学信网/手机号），工具不做代登录抓取；"
            "建议在平台内筛选收藏后，用「CSV 导入」把心仪岗位带回本工具统一管理：\n"
            "- 国家大学生就业服务平台（教育部·24365）：https://www.ncss.cn\n"
            "- 国聘（国投人力·国聘行动）：https://www.guopin.com\n"
            "- 实习僧：https://www.shixiseng.com\n"
            "- BOSS直聘：https://www.zhipin.com　｜　智联招聘：https://www.zhaopin.com\n"
            "- 前程无忧：https://www.51job.com　｜　牛客网：https://www.nowcoder.com\n"
            "- 猎聘：https://www.liepin.com　｜　拉勾：https://www.lagou.com\n\n"
            "**高校就业信息网**（你最该盯的渠道）：登录本校就业系统或就业公众号，很多企业只通过高校渠道招 2027 届实习/校招。")
        st.markdown("#### ⚠️ 合规与免责声明")
        st.warning(DISCLAIMER)
        st.markdown(
            "- 数据可能延迟/过期，投递前务必到官方链接核实；不自动代投，谨防封号与诈骗；\n"
            "- 默认遵守 robots.txt、低频抓取、勿商用；页面最近更新时间见左上角。")


if __name__ == "__main__":
    main()
