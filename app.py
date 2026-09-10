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
    df["企业官网"] = df.get("official_url", pd.Series(dtype=str)).fillna("")
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

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
        ["岗位列表", "🏆 为你推荐", "🎯 投递工作台", "我的收藏", "👤 我的资料", "说明与合规"])

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
                          unexpired_only=unexpired, since_days=since_days, limit=3000)
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
                    from ihub import resume
                    note = job.get("apply_note") or resume.apply_message(job)
                    edited = st.text_area("投递理由/开场白（可改）", value=note,
                                          key=f"note_{job['id']}_{state}", height=130)
                    if state == 1:
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

        c1, c2 = st.columns([1, 3])
        if c1.button("💾 保存资料", type="primary"):
            p = prof_mod.save(newvals)
            st.success(f"已保存到：{p}（下一条投递材料就会用你的信息）")
        if c2.button("♻️ 恢复示例资料"):
            p = prof_mod.save(dict(prof_mod.DEFAULT))
            st.info("已恢复为内置示例资料（罗广睿）")

    # ============ 说明 ============
    with tab6:
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
