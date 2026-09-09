"""Streamlit 网页：实习岗位聚合器 InternHub + 投递工作台
运行：streamlit run app.py  →  http://localhost:8501
"""
import csv
import datetime
import os

import pandas as pd
import streamlit as st

from ihub import config, db
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
    return df


def load_df(city, keyword, active_only, fake_only, favorite_only,
            unexpired_only, since_days):
    rows = db.query(city=city, keyword=keyword, active_only=active_only,
                    fake_only=fake_only, favorite_only=favorite_only,
                    unexpired_only=unexpired_only, since_days=since_days)
    return _display_df(rows)


def export_box_csv():
    rows = db.query(apply_state=1)
    if not rows:
        return None
    path = os.path.join(OUT_DIR, f"投递清单_{datetime.date.today().isoformat()}.csv")
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["岗位", "公司", "城市", "薪资", "截止日期", "来源", "投递链接"])
        for r in rows:
            w.writerow([r["title"], r["company"], r["city"], r["salary"],
                        r.get("deadline") or "", r["source"], r["link"]])
    return path


def gen_resume_for(job):
    from ihub import resume
    safe = resume._simplify_path_safe(str(job.get("company") or "") + "_" + str(job.get("title") or ""))
    path = os.path.join(OUT_DIR, f"{safe}_简历.docx")
    return resume.build_docx(job, path)


def main():
    st.title("🧭 实习岗位聚合器 InternHub")
    st.caption("聚合公开实习信息 · 投递材料按岗位定制 · 本地个人学习使用")

    db.init_db()

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
            for i, c in enumerate(cities, 1):
                with st.spinner(f"抓取 {c}…"):
                    jobs += crawler.fetch_city(c, max_pages=pages)
                bar.progress(i / total_cities if (total_cities := len(cities)) else 1)
            if enrich and jobs:
                with st.spinner("补抓截止时间（详情页）…"):
                    crawler.enrich_deadlines(jobs, cap=min(15, len(jobs)))
            res = db.upsert_jobs(jobs)
            st.success(f"解析 {len(jobs)} 条 → 新增 {res['inserted']} / 更新 {res['updated']}")
            st.rerun()

        st.divider()
        st.header("② 筛选")
        city_choices = list(dict.fromkeys(["全部"] + config.PROVINCE_LABELS + sorted(db.distinct_cities())))
        f_city = st.selectbox("按地区筛选（支持省份，如“山东”）", city_choices)
        f_keyword = st.text_input("关键词（岗位/公司/标签）", placeholder="例如：AIGC / 新媒体 / 嵌入式")
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

    tab1, tab2, tab3, tab4 = st.tabs(["岗位列表", "🎯 投递工作台", "我的收藏", "说明与合规"])

    # ============ 岗位列表 ============
    with tab1:
        city_arg = None if f_city == "全部" else f_city
        df = load_df(city_arg, f_keyword or None, active_only, fake_only, fav_only,
                     unexpired, since_days)
        if df.empty:
            st.info("📭 暂无数据：先在左侧选城市并点「立即抓取」。")
        else:
            today = datetime.date.today().isoformat()
            dl = df["截止时间"].astype(str).str[:10]
            df["状态"] = dl.apply(lambda x: "已截止" if (len(x) == 10 and x < today) else ("临近" if (len(x) == 10 and x <= today) else "可投"))
            st.caption(f"共 {len(df)} 条 · 勾选「投递箱」→ 保存后到「投递工作台」生成材料")
            cols = ["id", "title", "company", "city", "salary", "degree", "标签",
                    "截止时间", "状态", "投递箱", "source", "link", "favorite"]
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
                    "link": st.column_config.LinkColumn("投递链接（官方）"),
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

    # ============ 投递工作台 ============
    with tab2:
        st.warning(AUTOBOT_NOTE)
        box_rows = db.query(apply_state=1, active_only=False, limit=300)
        if not box_rows:
            st.info("投递箱是空的：到“岗位列表”勾选 🎯 后点「保存 投递箱+收藏」。")
        else:
            if st.button("📤 导出投递清单 CSV"):
                p = export_box_csv()
                st.success(f"已导出：{p}")
            st.caption(f"投递箱共 {len(box_rows)} 条，逐条处理：")
            for job in box_rows:
                title = str(job.get("title") or "")
                with st.expander(f"【{job.get('company')}】{title[:36]}｜{job.get('city')}｜{job.get('salary') or '—'}"):
                    st.markdown(f"官方链接：{job.get('link')}")
                    from ihub import resume
                    note = job.get("apply_note") or resume.apply_message(job)
                    edited = st.text_area("投递理由/开场白（可改）", value=note,
                                          key=f"note_{job['id']}", height=130)
                    c1, c2, c3, c4 = st.columns(4)
                    if c1.button("💾 保存理由", key=f"saven_{job['id']}"):
                        db.set_apply_note(job["id"], edited)
                        st.success("已保存")
                    if c2.button("📄 生成定制简历", key=f"cv_{job['id']}"):
                        try:
                            p = gen_resume_for(job)
                            st.success(f"已生成：{p}")
                        except Exception as e:
                            st.error(f"生成失败：{e}")
                    if c3.button("✅ 标记已投", key=f"done_{job['id']}"):
                        db.set_apply_state([(job["id"], 2)])
                        st.rerun()
                    if c4.button("➖ 移出", key=f"out_{job['id']}"):
                        db.set_apply_state([(job["id"], 0)])
                        st.rerun()

    # ============ 我的收藏 ============
    with tab3:
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

    # ============ 说明 ============
    with tab4:
        st.markdown("#### 使用说明")
        st.markdown(
            "1. 抓取 → 筛选 → 勾选 🎯投递箱 → 保存；\n"
            "2. 「投递工作台」逐条生成**投递理由**与**按岗位定制简历**(docx 输出到 投递文件/ 文件夹)，\n"
            "3. 点官方链接**手动投递**后标记“已投”；\n"
            "4. 自动更新：`python scheduler.py --hours 6`；其他来源可 CSV 导入：`python run_import.py 表.csv`。")
        st.markdown("#### ⚠️ 合规与免责声明")
        st.warning(DISCLAIMER)
        st.markdown(
            "- 数据可能延迟/过期，投递前务必到官方链接核实；不自动代投，谨防封号与诈骗；\n"
            "- 默认遵守 robots.txt、低频抓取、勿商用；页面最近更新时间见左上角。")


if __name__ == "__main__":
    main()
