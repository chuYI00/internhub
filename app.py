"""Streamlit 网页：实习岗位聚合器 InternHub + 投递工作台
运行：streamlit run app.py  →  http://localhost:8501
"""
import csv
import datetime
import os
import re
import sys

import pandas as pd
import streamlit as st

from ihub import config, db, ledger
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


def days_left(deadline):
    """距截止还剩几天：没日期 → None；已过 → 负数。"""
    s = str(deadline or "").strip()[:10]
    if len(s) != 10:
        return None
    try:
        d = datetime.date.fromisoformat(s)
    except ValueError:
        return None
    return (d - datetime.date.today()).days


def left_badge(n):
    """剩余天数的显示文案 + 颜色（临期 3 天标红 —— 这是最容易漏投的一类）。"""
    if n is None:
        return "—", "#8b98a9"
    if n < 0:
        return "已截止", "#8b98a9"
    if n == 0:
        return "今天截止", "#d1242f"
    if n <= 3:
        return f"剩 {n} 天", "#d1242f"
    if n <= 7:
        return f"剩 {n} 天", "#c77700"
    return f"剩 {n} 天", "#1a7f37"


def load_df(city, keyword, active_only, fake_only, favorite_only,
            unexpired_only, since_days, job_type=None, sort=None, open_only=False):
    rows = db.query(city=city, keyword=keyword, active_only=active_only,
                    fake_only=fake_only, favorite_only=favorite_only,
                    unexpired_only=unexpired_only, since_days=since_days,
                    job_type=job_type, sort=sort, open_only=open_only)
    return _display_df(rows)


def _card_html(r):
    """一条岗位的卡片（卡片视图用）。发布时间 / 截止日期 / 剩余天数 一眼可见。"""
    import html
    def e(x):
        return html.escape(str(x or ""))
    title, company = e(r.get("title")), e(r.get("company"))
    city = e(r.get("city"))
    pub = str(r.get("published_at") or "")[:10] or "—"
    pub_note = "（抓取日）" if str(r.get("published_src") or "") == "fetched" else ""
    dl = str(r.get("deadline") or "")[:10]
    n = days_left(dl)
    txt, color = left_badge(n)
    if dl and n is not None and n <= 3:
        badge = (f'<span style="background:{color};color:#fff;padding:2px 8px;'
                 f'border-radius:10px;font-size:12px;font-weight:700">⚠ {txt}</span>')
    else:
        badge = f'<span style="color:{color};font-size:12px;font-weight:600">{txt}</span>'
    link = e(r.get("official_url") or r.get("link") or "")
    off = "官方" if r.get("official_url") else "来源页"
    salary = e(r.get("salary"))
    return (
        '<div style="border:1px solid #2b3441;border-radius:12px;padding:11px 13px;'
        'margin-bottom:9px;background:#1b212b">'
        f'<div style="font-size:15px;font-weight:700;color:#e8edf4">{title}</div>'
        f'<div style="font-size:13px;color:#a3b0c2;margin-top:3px">'
        f'{company}　·　{city}　·　{salary}</div>'
        '<div style="font-size:12px;color:#6d7c90;margin-top:6px">'
        f'发布 {pub}<span style="font-size:11px">{pub_note}</span>'
        f'　｜　截止 {dl or "未公布"}　｜　{badge}'
        f'</div>'
        f'<div style="margin-top:7px"><a href="{link}" target="_blank" '
        f'style="color:#4a9eff;font-size:12.5px">前往投递（{off}）↗</a></div>'
        '</div>')


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


# 首次打开的新手引导条：4 步卡片，关掉后写 localStorage，之后不再出现。
# 用原生 HTML 组件渲染（Streamlit 自己没有 localStorage，得靠这段 JS 记住"看过了"）。
_ONBOARD_HTML = """
<style>
  *{box-sizing:border-box}
  body{margin:0;font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif}
  #ob{border:1px solid #2b6cb0;border-left:4px solid #2b6cb0;background:#16243a;
      border-radius:10px;padding:12px 14px;color:#e8edf4}
  #ob .step{font-size:11px;color:#7fb3ff;letter-spacing:1px;margin-bottom:5px}
  #ob h4{margin:0 0 5px;font-size:15px;color:#fff}
  #ob p{margin:0;font-size:13px;line-height:1.6;color:#c3d3e8}
  #ob b{color:#ffd479}
  #ob .row{margin-top:10px;display:flex;gap:8px;align-items:center}
  #ob button{border:1px solid #3d5a80;background:#1e3a5f;color:#e8edf4;border-radius:7px;
      padding:5px 13px;font-size:13px;cursor:pointer}
  #ob button.pri{background:#2b6cb0;border-color:#2b6cb0;color:#fff;font-weight:600}
  #ob button.link{background:none;border:none;color:#7d8fa6;font-size:12px;
      margin-left:auto;text-decoration:underline;cursor:pointer}
  #ob .dots{display:flex;gap:5px;margin-left:4px}
  #ob .dots i{width:6px;height:6px;border-radius:50%;background:#3d5a80;display:block}
  #ob .dots i.on{background:#7fb3ff;width:16px;border-radius:3px}
</style>
<div id="ob">
  <div class="step">第 <span id="s1">1</span> / 4 步 · 30 秒看懂怎么用</div>
  <h4 id="t"></h4>
  <p id="b"></p>
  <div class="row">
    <button id="prev">上一步</button>
    <button id="next" class="pri">下一步</button>
    <span class="dots" id="dots"></span>
    <button id="skip" class="link">看过了，别再显示</button>
  </div>
</div>
<script>
(function(){
  var KEY='ihub_onboard_v1', i=0;
  var S=[
    ['🎯 第一步：看岗位',
     '默认已经帮你选好 <b>昆明 + 大理</b>。用上面的「🔎 筛选与排序」挑出要投的，'
     + '排序选「截止时间（近→远）」能先看到<b>快截止</b>的；剩 ≤3 天的会<b>标红</b>。'],
    ['🏛 第二步：去官方页投',
     '点列表里的「<b>企业官网招聘</b>」列，直接到公司自己的招聘页 —— '
     + '<b>不要在第三方平台页投</b>（信息滞后、还容易被中间商截留）。'],
    ['🤖 第三步：网申让脚本填',
     '装好 Tampermonkey 后打开 <code>网申助手.user.js</code>，进网申页点右下角悬浮球 → '
     + '「🚀 填入空字段」。<b>70 类字段</b>自动填，认不出的教它一次就终身认识。'],
    ['📄 第四步：简历 + 备考',
     '「📄 简历定制」按岗位方向出<b>单页定向简历</b>；「📚 备考方案」倒推每天该干什么。'
     + '手机上翻：<b>备考冲刺资料/手机备考手册.html</b>。']
  ];
  function hide(){
    try{localStorage.setItem(KEY,'1')}catch(e){}
    document.getElementById('ob').style.display='none';
    try{window.parent.postMessage({isStreamlitMessage:true,type:'streamlit:setFrameHeight',height:0},'*')}catch(e){}
  }
  function draw(){
    document.getElementById('s1').textContent=(i+1);
    document.getElementById('t').textContent=S[i][0];
    document.getElementById('b').innerHTML=S[i][1];
    document.getElementById('prev').style.visibility=i? 'visible':'hidden';
    document.getElementById('next').textContent=(i===S.length-1)?'开始使用 🚀':'下一步';
    var d='';for(var k=0;k<S.length;k++){d+='<i class="'+(k===i?'on':'')+'"></i>'}
    document.getElementById('dots').innerHTML=d;
  }
  try{ if(localStorage.getItem(KEY)==='1'){ hide(); return; } }catch(e){}
  draw();
  document.getElementById('prev').onclick=function(){ if(i>0){i--;draw();} };
  document.getElementById('next').onclick=function(){
    if(i<S.length-1){ i++; draw(); } else { hide(); }
  };
  document.getElementById('skip').onclick=hide;
})();
</script>
"""


def render_onboarding():
    """首次打开才弹的 4 步引导条（关掉后写 localStorage，之后不再出现）。"""
    if st.session_state.get("_onboard_shown"):
        return
    st.session_state["_onboard_shown"] = True
    try:
        st.html(_ONBOARD_HTML, height=175)     # 1.63：st.html 替代已弃用的 components.v1.html
    except Exception:
        pass


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
    st.title("🎯 InternHub · 秋招工作台")
    st.caption("**主线：看岗位 → 官方投递 → 网申填表 → 定制简历 → 备考目标单位**　|　"
               "默认视图：**秋招 × 云南（昆明 / 大理）**　|　本地运行，资料不上传")
    st.caption("链接口径：**只有企业/单位自己的域名才叫「官方直达」**；"
               "招聘平台的页一律标「来源页/平台入口」；点开是搜索引擎的假直达已全部移除。")

    render_onboarding()

    db.init_db()
    db.backfill_official_urls()
    # v3 硬标准：发布时间不许为空（空的补抓取日，否则按发布时间排序时老岗位会顶到最前）
    try:
        db.fill_published_at()
    except Exception:
        pass

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
        st.caption("筛选与排序已上移到「🎯 岗位」页顶部（看岗位的地方就该能筛），"
                   "这里只留抓取设置。")

        st.divider()
        st.header("② 快速入口")
        st.markdown(
            "- 📱 [手机备考手册（在线版）](https://tobacco-study-card.app.workbuddy.host/)\n"
            "- 🤖 `网申助手.user.js` → 用 Tampermonkey 安装\n"
            "- 📖 `网申助手使用说明.md`（3 步上手）\n"
            "- 📁 `投递文件/` ← 生成的简历都在这里")
        if st.button("📂 打开「投递文件」文件夹"):
            try:
                os.startfile(OUT_DIR)              # noqa: S606 本机自用工具
            except Exception as _e:
                st.caption(f"打不开：{_e}")

        with st.expander("③ 维护（重生成 / 体检 / 清数据）", expanded=False):
            st.caption("改了资料或者页面出毛病，先点这两个。")
            if st.button("🔧 重新生成脚本（网申助手 + 采集助手）"):
                import subprocess
                _r = subprocess.run([sys.executable, "-m", "ihub.autofill"],
                                    cwd=ROOT_APP, capture_output=True, text=True,
                                    encoding="utf-8", errors="replace")
                st.success("网申助手已重新生成" if _r.returncode == 0 else f"失败：{_r.stderr[-300:]}")
            if st.button("🧭 补齐发布时间（空的记抓取日）"):
                n = db.fill_published_at()
                st.success(f"补齐 {n} 条（发布时间为空的已按抓取日填好）")
                st.rerun()
            st.caption("⚠️ 下面两个会改数据，想清楚再点。")
            if st.button("🧹 清空收藏", key="mt_clear_fav"):
                db.set_favorites([])
                st.success("已清空收藏")
            if st.checkbox("我确认要清空**投递箱**（把已勾选的待投全部归零）"):
                if st.button("❌ 执行清空投递箱", key="mt_clear_box"):
                    db.set_apply_state([(int(r["id"]), 0) for r in
                                        db.query(apply_state=1, active_only=False, limit=5000)])
                    st.success("投递箱已清空")
                    st.rerun()

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

    # 2026-09-16 收敛重构：12 个页签 → 4 个，主线「看岗位 → 官方投递 → 网申填表 → 定制简历 → 备考」。
    # 注意：同一个 tabN 会在此文件里出现多次（把原多个页签合并进一个），Streamlit 会把内容
    # 依次追加渲染到同一个页签 —— 所以下面 with tabN: 的编号必须与这里的 4 个页签一一对应。
    (tab1, tab2, tab3, tab4) = st.tabs(
        ["🎯 岗位", "📮 投递与网申", "📄 简历定制", "📚 备考方案"])

    # ---- 每个页签顶部一句「这一页帮你做什么」（v3：别让人猜这页是干嘛的）----
    with tab1:
        st.info("**这一页帮你做什么**：筛出昆明 + 大理要投的岗位 → 看**发布时间 / 截止日期 / 剩几天**"
                "（剩 ≤3 天标红）→ 点**企业官网**列去官方页投。　主线：**🔎 筛选与排序** → 勾选投递箱 → **🚀 广投**")
    with tab2:
        st.info("**这一页帮你做什么**：记每一笔投递，别「投了不知道投过」。"
                "⚠️ **烟草同批次只能报 1 个单位 1 个岗**，重复投递会在这里被拦下来。")
    with tab3:
        st.info("**这一页帮你做什么**：选岗位方向 → 生成**单页定向简历**（docx / pdf）+ "
                "可以直接粘进网申系统的文案。先点上面的主按钮。")
    with tab4:
        st.info("**这一页帮你做什么**：按考试日倒推每天该干什么、背什么、刷什么。"
                "📱 手机上翻：**备考冲刺资料/手机备考手册.html**（已发布成在线链接）。")

    # ============ 岗位列表 ============
    with tab1:
        # ---- 顶部横幅：烟草监控的最新公告（监控不占页签，在后台自动化跑）----
        try:
            from ihub import tobacco as _tb
            _seen = _tb.load_seen()
            _latest = sorted(_seen.values(),
                             key=lambda x: str(x.get("first_seen") or ""), reverse=True)[:3]
            if _latest:
                _titles = "　".join("· " + str(x.get("title") or "")[:32] for x in _latest)
                st.info(f"🍃 **烟草最新公告**（已见 {len(_seen)} 条）：{_titles}\n\n"
                        "→ 往下展开「🍃 烟草监控」看**报名窗口 / 剩余天数 / 是否限报 1 岗**")
            else:
                st.info("🍃 烟草监控还没扫描过 —— 往下展开「🍃 烟草监控」点一次「🔍 立即扫描一次」")
        except Exception as _e:                                   # 监控坏了也不能拖垮岗位页
            st.caption(f"烟草监控暂不可用：{_e}")

        # ---- 一级开关：秋招 / 实习（默认秋招；实习数据保留，切过去就能看）----
        job_type = st.radio("岗位类型（一级开关）", ["秋招", "实习", "全部"], horizontal=True,
                            key="lvl_job_type",
                            help="默认只看秋招。实习数据一条没删，切到「实习」就能看。")

        # ---- 筛选 + 排序（v3：城市多选默认昆明+大理；按发布时间/截止日期/公司名排序）----
        with st.container(border=True):
            st.markdown("**🔎 筛选与排序**")
            city_choices = list(dict.fromkeys(
                config.DEFAULT_CITIES + config.PROVINCE_LABELS + sorted(db.distinct_cities())))
            _def_cities = [c for c in ("昆明", "大理") if c in city_choices]
            f_cities = st.multiselect(
                "城市（可多选，默认昆明 + 大理；不选 = 不限）", city_choices,
                default=_def_cities, key="flt_cities",
                help="大理也投：本地生源竞争远小于昆明，别只盯昆明。")
            r1, r2 = st.columns([1.3, 1])
            f_keyword = r1.text_input("关键词（岗位/公司/标签）", key="flt_kw",
                                      placeholder="例如：国企 / 电气 / 嵌入式 / 信息化")
            sort_by = r2.selectbox("排序", db.SORT_OPTIONS, index=0, key="flt_sort",
                                   help="按发布时间看最新；按截止时间看「快截止的」先投。")
            r3, r4 = st.columns([1, 1])
            time_range = r3.radio("收录时间范围", ["全部", "近3天", "近7天", "近30天"],
                                  horizontal=True, key="flt_time")
            since_days = {"近3天": 3, "近7天": 7, "近30天": 30}.get(time_range)
            view_mode = r4.radio("视图", ["表格", "卡片"], horizontal=True, key="flt_view",
                                 help="卡片视图一眼看到发布时间 / 截止日期 / 剩几天")
            g1, g2, g3, g4, g5 = st.columns(5)
            open_only = g1.checkbox("🟢 报名中", value=False, key="flt_open",
                                    help="只看**有明确截止日期且还没过**的（没写截止日期的不算）")
            unexpired = g2.checkbox("只看未截止", value=True, key="flt_unexp",
                                    help="排除已过期的（没写截止日期的保留）")
            active_only = g3.checkbox("仅看有效", value=True, key="flt_active")
            fav_only = g4.checkbox("只看收藏", value=False, key="flt_fav")
            fake_only = g5.checkbox("只看风险", value=False, key="flt_fake")
            if open_only:
                st.caption("🟢 报名中 = 有截止日期且 ≥ 今天。**没写截止日期的岗位会被这条筛掉**"
                           "（那些用「只看未截止」来看）。")

        # ---- 📥 导入向导（v2 重构：4 条通道收敛成这 1 处 —— 原来岗位页/备考页各有一套，埋得深没人找得到）
        from ihub import wizard_ui
        with st.container(border=True):
            wizard_ui.render()

        f_city = "、".join(f_cities) if f_cities else "全部"
        df = load_df(f_cities, f_keyword or None, active_only, fake_only, fav_only,
                     unexpired, since_days, job_type=job_type, sort=sort_by,
                     open_only=open_only)
        if df.empty:
            st.info("📭 暂无数据：先在左侧选城市并点「立即抓取」，或用上面的「📥 导入向导」导入。")
        else:
            today = datetime.date.today().isoformat()
            dl = df["截止时间"].astype(str).str[:10]
            df["发布时间"] = df.get("published_at", pd.Series(dtype=str)).fillna("").astype(str).str[:10]
            df["剩余"] = df["截止时间"].apply(lambda x: (lambda n: left_badge(n)[0])(days_left(x)))
            df["状态"] = dl.apply(lambda x: "已截止" if (len(x) == 10 and x < today) else ("临近" if (len(x) == 10 and x <= today) else "可投"))

            if view_mode == "卡片":
                # 卡片视图：一眼看到发布时间 / 截止日期 / 剩几天（临期 3 天标红），
                # 但一次最多渲染 80 张，再多就卡了 —— 后面提示去用表格批量勾选。
                rows_r = df.to_dict("records")
                st.caption(f"共 {len(df)} 条 · 卡片视图最多显示 80 条"
                           "（要批量勾选投递箱请用「表格」视图）")
                st.markdown("".join(_card_html(r) for r in rows_r[:80]),
                            unsafe_allow_html=True)
                st.divider()
            else:
                st.caption(f"共 {len(df)} 条 · 勾选「投递箱」→ 保存后到「投递工作台」生成材料")
            cols = ["id", "title", "company", "city", "salary", "degree", "标签",
                    "发布时间", "截止时间", "剩余", "状态", "投递箱", "source", "link",
                    "企业官网", "favorite"]
            # 卡片视图下把表格收起来（卡片用来扫，表格用来勾投递箱）
            _holder = (st.expander("📋 展开表格（勾选投递箱 / 收藏）", expanded=False)
                       if view_mode == "卡片" else st.container())
            with _holder:
                edit = st.data_editor(
                    df[cols],
                    hide_index=True,
                    disabled=[c for c in cols if c not in ("投递箱", "favorite")],
                    column_config={
                        "id": None,
                        "title": st.column_config.TextColumn("岗位"),
                        "company": "公司", "city": "城市", "salary": "薪资", "degree": "学历",
                        "标签": "标签",
                        "发布时间": st.column_config.TextColumn(
                            "发布时间", help="来源没给发布日期的，这里记的是抓取日（卡片里会标「抓取日」）"),
                        "截止时间": "截止时间",
                        "剩余": st.column_config.TextColumn(
                            "剩余", help="距截止还剩几天；≤3 天是临期，最容易漏投"),
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
            export = df[["title", "company", "city", "salary", "degree", "发布时间",
                          "截止时间", "剩余", "状态", "企业官网", "link"]].copy()
            export.columns = ["岗位", "公司", "城市", "薪资", "学历", "发布时间", "截止日期",
                              "剩余天数", "状态", "官方投递入口", "原平台链接"]
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

    # ============ 🏆 为你推荐（并入 🎯 岗位）============
    with tab1:
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

        rows_r = db.query(cities=f_cities or None, keyword=f_keyword or None,
                          active_only=active_only, open_only=open_only,
                          unexpired_only=unexpired, since_days=since_days,
                          job_type=job_type, sort=sort_by, limit=3000)
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

        # ---- 📄 岗位 → 简历定制 联动（第 3 步重构）----
        # Streamlit 的页签不能由程序切换，所以这里做成「带过去」：
        # 点一下就把公司/岗位写进「📄 简历定制」页的输入框，切过去直接粘 JD 就行。
        st.divider()
        st.markdown("#### 📄 拿一条岗位去做定向简历")
        from ihub import linkcheck as LC           # 局部导入：这块比「链接体检」区块先执行
        _lk_rows = db.query(cities=f_cities or None,
                           keyword=f_keyword or None, active_only=active_only, limit=300)
        if not _lk_rows:
            st.caption("岗位列表为空 —— 先在侧边栏抓取或导入岗位。")
        else:
            _lk_opts = [f'{(r.get("company") or "（无公司名）")}｜{r.get("title") or ""}｜{r.get("city") or ""}'
                        for r in _lk_rows]
            _lk_pick = st.selectbox("选一条岗位（也可以直接去「📄 简历定制」页手填）",
                                    _lk_opts, key="lk_pick")
            _lk_i = _lk_opts.index(_lk_pick)
            _lk_job = _lk_rows[_lk_i]
            _lk_b1, _lk_b2 = st.columns([1, 3])
            if _lk_b1.button("📄 定制这份简历 →", key="lk_to_tailor", type="primary"):
                # 直接写 key（这一块在「📄 简历定制」页签之前渲染，赋值合法）
                st.session_state["tk_co"] = str(_lk_job.get("company") or "")
                st.session_state["tk_jt"] = str(_lk_job.get("title") or "")
                st.session_state["tk_jd"] = str(_lk_job.get("jd_text") or _lk_job.get("description") or "")
                st.session_state["lk_done"] = _lk_pick
                st.rerun()
            _done = st.session_state.pop("lk_done", None)
            if _done:
                st.success(f"✅ 已把「{_done}」带到「📄 简历定制」页签（公司 / 岗位已填好）——"
                           "点上面的页签切过去，粘上 JD 就能生成定向简历和网申文案。")
            with st.expander("这条岗位的信息（核对一下再带过去）"):
                st.markdown(f'**公司**：{_lk_job.get("company") or "—"}　**岗位**：{_lk_job.get("title") or "—"}　'
                            f'**城市**：{_lk_job.get("city") or "—"}')
                _lj_off = str(_lk_job.get("official_url") or "")
                _lj_link = str(_lk_job.get("link") or "")
                if _lj_off and not LC.is_any_search(_lj_off):
                    st.markdown(f"✅ **官方投递**：{_lj_off}")
                else:
                    st.markdown("✅ **官方投递**：—（该来源没有官方入口，去「🌏 云南秋招渠道地图」找）")
                if _lj_link:
                    st.caption(f"来源页（非官方，点开是采集到它的平台）：{_lj_link}")
                _jd_prev = str(_lk_job.get("jd_text") or _lk_job.get("description") or "")
                if _jd_prev:
                    st.caption("JD 预览：" + _jd_prev[:300])
                else:
                    st.caption("这条岗位没有采集到 JD 正文 —— 到官方页面把「任职要求」整段复制，"
                               "带回「📄 简历定制」页的 JD 框里，方向识别才准。")

    # ============ 🎯 投递工作台（并入 📄 简历定制）============
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

    # ============ 我的收藏（并入 🎯 岗位）============
    with tab1:
        df_fav = load_df(None, None, active_only, False, True, unexpired, since_days)
        if df_fav.empty:
            st.info("还没有收藏。")
        else:
            st.dataframe(df_fav[["title", "company", "city", "salary", "截止时间", "source", "link"]],
                         hide_index=True,
                         column_config={"title": "岗位", "company": "公司", "city": "城市",
                                        "salary": "薪资", "截止时间": "截止时间", "source": "来源",
                                        "link": st.column_config.LinkColumn(
                                            "投递（原平台）",
                                            help="来源平台的原始页面 —— 不等于官方投递页，"
                                                 "官方入口看「🎯 岗位」页的渠道地图")},
                         width="stretch")

    # ============ 👤 我的资料（并入 📮 投递与网申）============
    with tab2:
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

    # ============ 📮 网申跟踪（并入 📮 投递与网申）============
    with tab2:
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

        # ---- ⛔ 烟草 1 单位 1 岗的强拦截（待确认的登记先存在这里）----
        _pend = st.session_state.get("ledger_pending")
        if _pend:
            st.error("⛔ **这条不能直接登记 —— 会被取消资格**")
            st.error(_pend["check"]["msg"])
            _c1, _c2 = st.columns([1, 1])
            if _c1.button("❌ 算了，不登记", key="pend_cancel"):
                st.session_state.pop("ledger_pending", None)
                st.rerun()
            if _c2.button("我已确认要改报这一条（先把前一条改成「未通过」）", key="pend_force"):
                db.app_add(_pend["args"]["company"], _pend["args"]["title"], _pend["args"]["city"],
                           _pend["args"]["url"], _pend["args"]["job_type"],
                           _pend["args"]["deadline"], _pend["args"]["note"] + "（已人工确认改报）")
                st.session_state.pop("ledger_pending", None)
                st.warning("已登记，但请立刻把上一条的进度改成「未通过」，并到官方系统确认前一条没有占名额。")
                st.rerun()

        with st.expander("➕ 手动添加一条（官网/公众号看到的岗位）"):
            with st.form("add_app", clear_on_submit=True):
                a1, a2, a3 = st.columns(3)
                comp = a1.text_input("公司")
                tit = a2.text_input("岗位")
                cty = a3.text_input("城市", value=(f_cities[0] if f_cities else "潍坊"))
                a4, a5, a6 = st.columns(3)
                url = a4.text_input("网申/公告链接")
                dl2 = a5.text_input("截止日期（YYYY-MM-DD）")
                jt = a6.selectbox("类型", ["秋招", "实习"])
                note0 = st.text_input("备注")
                if st.form_submit_button("添加"):
                    _chk0 = ledger.check_new(comp, tit, db.app_list(limit=2000))
                    if _chk0["level"] == "block":
                        # 烟草铁律：同批次只能 1 单位 1 岗 —— 不静默写入，弹红框让人确认
                        st.session_state["ledger_pending"] = {
                            "check": _chk0,
                            "args": {"company": comp, "title": tit, "city": cty, "url": url,
                                     "job_type": jt, "deadline": dl2, "note": note0},
                        }
                        st.rerun()
                    db.app_add(comp, tit, cty, url, jt, dl2, note0)
                    if _chk0["level"] == "warn":
                        st.warning(_chk0["msg"])
                    st.success("已添加")
                    st.rerun()

        if st.button("⬇️ 把「投递箱」里的岗位加入跟踪"):
            ids = [r["id"] for r in db.query(apply_state=1, limit=500)]
            n = db.app_add_from_job_ids(ids) if ids else 0
            st.success(f"已加入 {n} 条（重复的自动跳过）")

        # ---- 📥 网申助手 → 台账：填完/投完在页面上记一笔，复制回来粘贴入库 ----
        with st.expander("📥 从网申助手粘贴导入（投完一家就记一笔，防「投了不知道投过」）",
                         expanded=False):
            st.caption("用法：在网申页面右下角「📝 网申助手」面板里点 **「📮 记录本次投递」** → "
                       "再点 **「📋 复制待同步记录」** → 粘到下面这个框 → 点导入。\n\n"
                       "支持网申助手复制的 TSV、Excel/飞书另存的 CSV、以及手打的一行一条"
                       "（`公司 | 岗位 | 城市 | 状态`）。"
                       "**烟草的记录在这里就会被拦住** —— 同一批次只能报 1 个单位 1 个岗位。")
            _paste = st.text_area("粘贴投递记录", height=140, key="ledger_paste",
                                  placeholder="公司\t岗位\t城市\t状态\t投递日期\t链接\t备注\n"
                                              "云南中烟工业有限责任公司\t设备运维\t昆明\t已投\t2026-09-16\t\thttps://…")
            _lc1, _lc2 = st.columns([1, 3])
            if _lc1.button("📥 解析并预览", key="ledger_parse", type="primary") and _paste.strip():
                _parsed = ledger.parse_ledger_text(_paste)
                if not _parsed:
                    st.warning("没解析出记录 —— 检查一下是不是有「公司」这一列。")
                else:
                    st.session_state["ledger_plan"] = ledger.merge_plan(_parsed, db.app_list(limit=2000))
                    st.session_state["ledger_parsed"] = _parsed
            _plan = st.session_state.get("ledger_plan")
            if _plan:
                st.markdown("**预览：**" + ledger.summary_line(_plan))
                if _plan["new"]:
                    st.markdown("**将新增**")
                    st.dataframe(pd.DataFrame(_plan["new"]), hide_index=True, width="stretch")
                if _plan["update"]:
                    st.markdown("**已存在 → 只更新状态**")
                    st.dataframe(pd.DataFrame(
                        [{**rec, "原状态": hit.get("stage"), "记录id": hit.get("id")}
                         for rec, hit in _plan["update"]]), hide_index=True, width="stretch")
                if _plan["conflict"]:
                    st.error(f"⛔ {len(_plan['conflict'])} 条被拦截（**不会入库**）：")
                    for _rec, _chk in _plan["conflict"]:
                        st.error(f"「{_rec['company']}｜{_rec.get('title','')}」—— {_chk['msg']}")
                _ok = st.checkbox("我已核对，确认导入（被拦截的不会入库）", key="ledger_ok")
                if st.button("✅ 确认导入", key="ledger_commit", type="primary") and _ok:
                    _n_add = _n_up = 0
                    for _rec in _plan["new"]:
                        db.app_add(company=_rec["company"], title=_rec.get("title", ""),
                                   city=_rec.get("city", ""), url=_rec.get("url", ""),
                                   job_type="秋招", deadline="", note=_rec.get("note", ""))
                        _n_add += 1
                    for _rec, _hit in _plan["update"]:
                        _st = _rec.get("stage") or "已投"
                        if _st in db.STAGES:
                            db.app_update(int(_hit["id"]), stage=_st)
                            _n_up += 1
                    st.success(f"已导入：新增 {_n_add} 条，更新状态 {_n_up} 条；"
                               f"拦截 {len(_plan['conflict'])} 条。")
                    st.session_state.pop("ledger_plan", None)
                    st.rerun()
            st.caption("台账字段口径（导出的清单也按这个来）：公司 ｜ 岗位 ｜ 城市 ｜ 状态 ｜ "
                       "投递日期 ｜ 链接 ｜ 备注。")

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

    # ============ 🔍 链接体检（并入 📮 投递与网申）============
    with tab2:
        from ihub import linkcheck as LC

        st.markdown("#### 🔍 链接体检（每条渠道链接到底能不能点）")
        st.caption("标准来自《重构指令》：**真实可达（HTTP 200）+ 页面确实属于该单位 + 是投递入口本身**"
                   "（不是搜索页、不是平台转发页）。只有 **A 级**能当「官方投递直达」主按钮。")

        _res = LC.load_saved()
        if not _res:
            st.info("还没有体检数据。在本机跑一次即可生成：`venv\\Scripts\\python.exe run_linkcheck.py`")
        else:
            _s = LC.summary(_res)
            _m = st.columns(5)
            _m[0].metric("受检链接", _s["total"])
            _m[1].metric("A 官方直达", _s["A"], help="可以直接当投递主按钮")
            _m[2].metric("P 平台入口", _s["P"], help="招聘平台自己的页，不是企业官方页")
            _m[3].metric("C 淘汰", _s["C"], help="伪直达 / 死链 —— 已全部从按钮里移除")
            _m[4].metric("D 待复查", _s["D"], help="沙箱网络不通或撞反爬，本机浏览器点一次即可")
            st.caption(f"体检时间：{LC.saved_at() or '（未知）'}")

            _fake = [r for r in _res if r["grade"] == "C"]
            if _fake:
                with st.expander(f"❌ C 级：{len(_fake)} 条已淘汰（这些**不会再出现在任何按钮里**）",
                                 expanded=False):
                    st.caption("它们点开只是搜索引擎结果页（百度 / 搜狗微信）或已经打不开 —— "
                               "留着只会让人以为工具坏了，所以全删了，换成「去哪个栏目敲什么词」的文字说明。")
                    for _r in _fake[:40]:
                        st.markdown(f"- <small>{_r['label']}　"
                                    f"<a href=\"{_r['url']}\" target=\"_blank\">🔗 打开看</a>　"
                                    f"—　{_r['reason']}</small>",
                                    unsafe_allow_html=True)

            _d = [r for r in _res if r["grade"] == "D"]
            if _d:
                with st.expander(f"🔎 D 级：{len(_d)} 条待你在本机点一次确认", expanded=False):
                    st.caption("沙箱里被 TLS 拦截 / 连接重置 / 撞上反爬（403·412·418）—— "
                               "**这不代表链接坏**，只是这一侧测不了。你浏览器打开正常就是好的。")
                    for _r in _d:
                        st.markdown(f"- <small>{_r['label']}　"
                                    f"<a href=\"{_r['url']}\" target=\"_blank\">🔗 点我验证</a>　"
                                    f"—　{_r['reason']}</small>",
                                    unsafe_allow_html=True)

            _a = [r for r in _res if r["grade"] == "A"]
            with st.expander(f"✅ A 级：{len(_a)} 条官方直达（本机验证通过）", expanded=False):
                for _r in _a:
                    st.markdown(f"- <small>{_r['label']}　`{_r['url'][:70]}`</small>",
                                unsafe_allow_html=True)

        st.caption("在本机重跑体检：`venv\\Scripts\\python.exe run_linkcheck.py`　"
                   "（结果写入 data/link_health.json，网页读它；人工版在 `链接体检报告.md`）")

    # ============ 🛰 秋招渠道（并入 🎯 岗位）============
    with tab1:
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
            st.info("秋招岗位库暂无数据：用本页顶部的「📥 导入我的岗位表」把你的岗位表导进来（飞书只读表也能解），"
                    "或用下面渠道自己找（找到后按同样方式导入）。")
        else:
            import pandas as _pd
            from ihub import linkcheck as _LC

            qdf = _pd.DataFrame(q_rows)
            # 第 2 步硬标准：**只有企业自己的域名才能叫「官方报名」**。
            # 来源平台的链接（实习僧详情页、高校就业网）单独一列，标清平台名，
            # 不让它冒充官方入口 —— 之前用户就是被这种「看着像官方」的链接骗过。
            qdf["官方报名"] = qdf["official_url"].fillna("").map(
                lambda u: u if (u and not _LC.is_any_search(u)) else "")
            qdf["来源页"] = qdf["link"].fillna("")
            qdf["截止"] = qdf["deadline"].fillna("")
            st.dataframe(
                qdf[["company", "title", "city", "batch", "degree", "截止",
                     "官方报名", "来源页", "source"]],
                hide_index=True,
                column_config={
                    "company": "单位", "title": "岗位", "city": "城市", "batch": "届别",
                    "degree": "学历", "截止": "截止日期",
                    "官方报名": st.column_config.LinkColumn(
                        "✅ 官方报名（企业域名）",
                        help="只有企业/单位自己的域名才显示在这里；为空＝该来源没有官方入口"),
                    "来源页": st.column_config.LinkColumn(
                        "来源页（非官方）", help="采集到这条岗位的原始平台页面，进去后仍可用网申助手填表"),
                    "source": "来源",
                },
                width="stretch", height=320,
            )
            _no_off = int((qdf["官方报名"] == "").sum())
            if _no_off:
                st.caption(f"其中 {_no_off} 条没有官方入口（来源平台只给了自己的详情页）—— "
                           f"按「公司」去「🌏 云南秋招渠道地图」或「全网平台入口」找官方报名页，找到后可在"
                           f" `data/official_urls.json` 里补一条，下次自动匹配。")
            if st.button("⬇️ 把上面这些秋招岗位加入「📮 网申跟踪」"):
                n = db.app_add_from_job_ids([r["id"] for r in q_rows])
                st.success(f"已加入 {n} 条（重复自动跳过），去「📮 网申跟踪」维护进度")

        st.divider()
        st.markdown("**② 各平台怎么搜**（⚠️ 原来的「一键搜索直达」已按重构指令删除）")
        st.caption("删掉的原因：那些链接拼的是「百度里搜某平台」，**点开只是百度结果页**，"
                   "不是岗位页 —— 你还得在结果里自己翻，等于没直达，反而让人以为工具坏了。"
                   "现在改成：告诉你**去哪个栏目、敲什么词**，比一条假链接有用。")
        s1, s2 = st.columns([1, 2])
        scity = s1.selectbox("搜索城市", ["昆明", "大理", "云南", "全国"], key="srch_city")
        skw = s2.text_input("搜索关键词（专业方向/岗位，如 物联网、电气、信息科技）",
                            value="物联网", key="srch_kw")
        _notes = cc.manual_search_notes(city="" if scity == "全国" else scity, keyword=skw)
        with st.expander(f"📋 去这 {len(_notes)} 个平台搜，每个平台的筛法（点开看）", expanded=True):
            for _name, _site, _how in _notes:
                st.markdown(f"- **{_name}**（`{_site}`）：{_how}")

        st.divider()
        st.markdown("**③ 七大板块官方入口**（点开即到官方/公开页面）")
        for title, items in cc.CHANNEL_GROUPS:
            with st.expander(title, expanded=False):
                c = st.columns(2)
                for i, (name, url) in enumerate(items):
                    if url:
                        c[i % 2].markdown(f"- [{name}]({url})")
                    else:
                        # 原先是百度/搜狗搜索链接 —— 伪直达，已换成一句说明
                        c[i % 2].markdown(f"- <small>{name}</small>", unsafe_allow_html=True)
        st.caption("提示：BOSS/智联/牛客等需登录后查看；本页只提供官方入口，**不再有任何"
                   "「点开只是搜索引擎」的伪直达**。")

    # ============ 📚 备考方案 ============
    with tab4:
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

        # ============ 🎓 备考方案生成器（第 4 步重构：通用，不写死烟草）============
        st.markdown("#### 🎓 备考方案生成器（选目标 → 自动出方案）")
        st.caption("不是「一堆课程链接 + 加油」，而是像教培老师那样：**考什么、分值怎么分、"
                   "该抓什么可以放弃什么、还剩 N 天每天几点干什么、哪些东西必须背下来**。")
        from ihub import studyplan as sp

        _g1, _g2, _g3, _g4 = st.columns([2, 1.4, 1.2, 1])
        _target = _g1.selectbox("① 目标单位", sp.targets(), key="sp_target")

        # 自定义：允许直接填一个不在列表里的单位名
        _custom = _g1.text_input("上面没有？直接填单位名（填了就按它出方案）", key="sp_custom",
                                 placeholder="例如：云南省交通投资建设集团")
        if _custom.strip():
            _target = _custom.strip()

        _role = _g2.text_input("② 目标岗位（决定专业知识考哪套）", key="sp_role",
                               placeholder="如：设备运维 / 信息化 / 电气")
        _sp_short = sp.profile_of(_target)["short"]
        _default_date = sp.default_exam_date(_sp_short)
        _edate = _g3.text_input("③ 考试日期（YYYY-MM-DD）", value=_default_date, key="sp_date")
        _hours = _g4.number_input("④ 每天可学(小时)", 1, 14, 6, 1, key="sp_hours")

        if st.button("🎓 生成备考方案", type="primary", key="sp_gen"):
            st.session_state["sp_plan"] = sp.generate(
                _target, role=_role, exam_date=_edate, hours=int(_hours))

        _plan = st.session_state.get("sp_plan")
        if not _plan:
            st.info("填好上面四项，点「🎓 生成备考方案」。"
                    "不知道考试日期也没关系 —— 会按往年的公告节奏给个默认值，你可以改。")
        else:
            _n = _plan["days_left"]
            _k1, _k2, _k3, _k4 = st.columns(4)
            _k1.metric("剩余天数", f"{_n} 天" if _n > 0 else "已过期")
            _k2.metric("每天", f'{_plan["hours_per_day"]} 小时')
            _k3.metric("总可用", f'{_plan["total_hours"]} 小时')
            _k4.metric("专业知识方向", _plan["role_key"])
            if _n <= 0:
                st.error("考试日期填的是过去的日期（或没填对）—— 改成未来日期再生成一次，"
                         "阶段划分才会按剩余天数倒推。")
            elif _n <= 21:
                st.warning(f"⏰ **只剩 {_n} 天** —— 方案已自动切成「冲刺模式」："
                           "不铺新知识，只做整卷计时 + 背必背清单 + 复盘错题。")
            else:
                st.success(f"距考试 {_n} 天，方案按「基础 → 强化 → 冲刺 → 考前一周」倒推。")
            st.info(_plan["note"] + ("\n\n⏰ " + _plan["exam_note"] if _plan["exam_note"] else ""))

            _md = sp.to_markdown(_plan)
            _d1, _d2 = st.columns([1, 3])
            _d1.download_button("⬇ 下载 Markdown", data=_md.encode("utf-8"),
                                file_name=f'备考方案_{_plan["short"]}.md', mime="text/markdown",
                                key="sp_dl_md")
            if _d2.button("💾 生成 Word（.docx）并保存到「备考冲刺资料」", key="sp_save"):
                _p_md = sp.save_markdown(_plan)
                _p_docx = sp.save_docx(_plan, _p_md)
                if _p_docx:
                    st.success(f"已保存：{_p_docx}")
                else:
                    st.warning(f"Word 生成失败，但 Markdown 已存到：{_p_md}")

            with st.container(height=560):
                st.markdown(_md)

        st.divider()
        st.markdown("**✅ 打卡（本地保存，按目标分别记录）**")
        from ihub import study
        _tname = _plan["target_raw"] if _plan else _target
        checks = study.load_checks()
        cur = dict(checks.get(_tname, {}))
        changed = False
        for i, it in enumerate(study.CHECK_ITEMS):
            v = st.checkbox(it, value=bool(cur.get(str(i), False)), key=f"chk_{_tname}_{i}")
            if v != bool(cur.get(str(i), False)):
                cur[str(i)] = v
                changed = True
        if changed:
            checks[_tname] = cur
            study.save_checks(checks)
            st.caption("已保存进度 ✅")

        st.divider()
        # v2 重构：导入入口已收敛到「🎯 岗位」页顶部的「📥 导入我的岗位表」向导，这里只留指路牌
        st.info("**导入岗位表**统一在「🎯 岗位」页顶部的「📥 导入我的岗位表」—— "
                "上传文件 / 复制粘贴 / 飞书抓包解码 / 截图 OCR 四条通道都在那一处。"
                "（原来这一页也有一套，入口重复才没人找得到）")

    # ============ 📄 简历定制（粘贴 JD → 定向简历 + 网申文案）（并入 📄 简历定制）============
    with tab3:
        from ihub import tailor as _tk
        st.markdown("#### 📝 简历定制与网申文案")
        st.caption("粘贴岗位 JD → 自动识别岗位方向 → 生成对应侧重的简历（docx / pdf）"
                   "与网申各栏文案。全部在本机完成，不联网、不上传。")
        st.caption("💡 从「🎯 岗位」页点「📄 定制这份简历」可以**把公司和岗位直接带过来**，"
                   "这里的输入框会自动填好 —— 你只要把 JD 粘进来。")

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

    # ============ 🌏 云南秋招（昆明 / 大理 渠道地图）（并入 🎯 岗位）============
    with tab1:
        from ihub import yunnan as yn
        from ihub import platforms as P

        st.markdown("#### 🌏 云南秋招投递渠道地图（昆明 / 大理）")
        st.caption("通用平台抓不到的（要登录、动态渲染、只走公众号）这里用「渠道地图」兜住："
                   "每个单位一条。**✅ 官方直达**＝该单位自己的域名，可直接当投递入口；"
                   "**🔎 搜索兜底**＝点开是搜索引擎结果页，只用来找当期公告，不是投递入口。")
        st.info("**你的定位**：2027 届 · 昆明 + 大理 · 央国企为主 · 不限企业类型 · 重点备考烟草。"
                "下面按「与你专业的契合度」排了序，★★★★ 以上的就是最该投的。")

        # ────────────── 全网平台入口（BOSS / 智联 / 牛客 / 国聘 / 24365 …）──────────────
        st.markdown("##### 🌐 全网平台入口（点一下就到该平台官网，再按下面教的词去搜）")
        st.caption("实测结论：BOSS直聘、智联、前程无忧、猎聘、牛客、国聘网、24365、高校人才网 "
                   "**全是前端渲染**，静态爬虫拿不到岗位（硬爬违反 robots、随时失效）。"
                   "测过之后只有 24365 一个**支持用链接直接发起站内搜索**，其余平台都改成"
                   "「打开官网 + 把该敲的关键词写清楚」—— **不再编一条点开是搜索页的假直达**。")

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
                    # 只有真能"用链接发起站内搜索"的平台才给第二个按钮（实测只有 24365）；
                    # 其余平台不编假直达，改成把该敲的关键词写在下面。
                    _search = P.in_site_search(_p)
                    if _search:
                        _b = st.columns([1, 1])
                        _b[0].link_button("🔗 打开官网", _p["url"], key=f"pl_u_{_cat[:2]}_{_j}")
                        _b[1].link_button("🔍 看云南岗位（已带关键词）", _search,
                                          key=f"pl_s_{_cat[:2]}_{_j}")
                    else:
                        st.link_button("🔗 打开官网", _p["url"], key=f"pl_u_{_cat[:2]}_{_j}")
                        st.caption("这个平台不支持用链接直接搜 —— 进站后在搜索框敲："
                                   "`昆明` / `大理` ＋ 专业词（嵌入式 · 物联网 · 自动化 · 电子信息）"
                                   "＋ `应届生`。**换几个词搜**，只搜一个词会漏掉一半岗位。")
                    st.markdown("")

        with st.expander("🔗 全部平台官方入口（一键复制，也能存到手机）", expanded=False):
            st.caption("⚠️ 这里**不再有「百度站内搜」那种链接**了 —— 实测它们只会打开百度页，"
                       "不是目标页面，等于没直达（已按重构指令全部移除）。"
                       "下面每条都是真实可达的官方入口。")
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
            st.caption("标 **✅ 官方直达** 的是该单位自己的域名（体检过）；"
                       "拿不到官方入口的会明写「搜索兜底」，**不拿假直达冒充**。")

        st.divider()
        st.markdown("##### 🎯 先看这些（★★★☆ 以上，按契合度排序）")
        for u in yn.for_me():
            with st.expander(f'{u["heat"]}　{u["name"]}　—　{u["fit"][:34]}…'):
                cols = st.columns([3, 1])
                with cols[0]:
                    for _what, _link in yn.official_links(u):
                        st.markdown(f'**✅ {_what}（官方直达）**：{_link}')
                    if not yn.has_official(u):
                        st.markdown("**✅ 官方直达**：—（该单位没有独立网申页，走上级集团/公众号统一发布）")
                    if u.get("apply_note"):
                        st.caption("说明：" + u["apply_note"])
                    st.caption(f'🔎 搜索兜底（点开是搜索引擎，只用来找公告）：{u["search"]}')
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
                    bits = [f'✅ [{_what}（官方直达）]({_link})' for _what, _link in yn.official_links(u)]
                    if not bits:
                        bits.append("✅ 官方直达：—（走上级集团/公众号统一发布）")
                    bits.append(f'🔎 [搜索兜底]({u["search"]})')
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

    # ============ 🍃 烟草监控（并入 🎯 岗位；公告另在岗位页顶部出横幅）============
    with tab1:
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

    # ============ 说明（不再占页签，收进侧边栏）============

    with st.sidebar.expander("ℹ️ 使用说明与合规", expanded=False):
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
