# -*- coding: utf-8 -*-
"""导入向导的网页层（Streamlit）—— 四条通道共用一个「解析 → 映射 → 确认 → 入库」流程。

放在独立模块的原因：app.py 已经 1100 行，而向导自己就有预览表、映射下拉、确认按钮一整套状态；
单独放既能让 app.py 只留一行调用，也能让冒烟测试直接断言这些组件在不在。

注意：**这里绝不能用 st.tabs** —— 冒烟测试断言"整页恰好 4 个页签"，
多一组就会把计数顶开（历史上页签数对不上出过渲染错位的事故）。通道选择用 radio。
"""
from __future__ import annotations

import streamlit as st

from . import wizard as wz

CHANNELS = ["① 上传 CSV / Excel", "② 复制粘贴", "③ 抓包解码", "④ 截图 OCR"]

_GUIDE = "飞书只读表格导出实操指南.md"


def _reset():
    for k in ("wz_parsed", "wz_mapping", "wz_chan"):
        st.session_state.pop(k, None)


def _set_parsed(res: dict):
    if not res or not res.get("rows"):
        return False
    st.session_state["wz_parsed"] = res
    st.session_state["wz_mapping"] = wz.guess_mapping(res["headers"], res["rows"])
    return True


def _render_mapping(parsed: dict):
    """预览 + 字段映射确认。"""
    headers = parsed["headers"]
    rows = parsed["rows"]
    st.success(f"✅ 解析到 **{len(rows)} 行 × {len(headers)} 列**"
               + ("（含表头）" if parsed.get("has_header") else "（**没认出表头**，第一行也当数据）"))
    for w in parsed.get("warnings") or []:
        st.warning("提醒：" + w)

    with st.expander("👀 看一眼原始表格（前 8 行）", expanded=True):
        import pandas as pd
        prev = pd.DataFrame(rows[:8], columns=headers or None)
        st.dataframe(prev, hide_index=True, width="stretch")

    st.markdown("**字段映射**　—— 你的列名跟下面的对不上就自己改；没用到的列**不会丢**，会并进备注。")
    opts = ["（这一列不导入）"] + [f"{i + 1}. {h or '（空列名）'}" for i, h in enumerate(headers)]
    mp = dict(st.session_state.get("wz_mapping") or {})
    c1, c2 = st.columns(2)
    new_mp = {}
    for i, (key, label, required) in enumerate(wz.STANDARD_FIELDS):
        cur = mp.get(key)
        idx = (cur + 1) if isinstance(cur, int) and 0 <= cur < len(headers) else 0
        box = (c1 if i % 2 == 0 else c2).selectbox(
            label + (" *" if required else ""), opts, index=idx, key=f"wz_map_{key}")
        new_mp[key] = opts.index(box) - 1
    st.session_state["wz_mapping"] = new_mp

    if new_mp.get("title", -1) < 0:
        st.error("「岗位名称」必须选一列 —— 没有岗位名的行不会被导入。")

    jobs, skipped = wz.build_jobs(headers, rows, new_mp,
                                  source=parsed.get("source") or "导入向导")
    st.info(f"按当前映射能入库 **{len(jobs)} 条**"
            + (f"（{skipped} 行没有岗位名，会被跳过）" if skipped else "")
            + "　·　下方勾选确认后才会真正写入")

    with st.expander("🔍 预览转换后的前 5 条（确认岗位名没被认错列）", expanded=False):
        import pandas as pd
        st.dataframe(pd.DataFrame([{
            "岗位": j["title"], "公司": j["company"], "城市": j["city"],
            "截止": j["deadline"], "链接": j["link"][:40], "备注": j["description"][:60],
        } for j in jobs[:5]]), hide_index=True, width="stretch")

    ok = st.checkbox("我已核对，确认导入", key="wz_ok")
    if st.button("✅ 确认导入", type="primary", key="wz_commit", disabled=not ok):
        if ok:
            res = wz.commit(jobs)
            st.success(f"已入库：新增 {res.get('inserted', 0)} 条，"
                       f"更新 {res.get('updated', 0)} 条"
                       + (f"，跳过重复 {res.get('skipped_dup', 0)} 条" if res.get("skipped_dup") else ""))
            _reset()
            st.rerun()


def render():
    """岗位页顶部的「📥 导入我的岗位表」一级区块。"""
    st.markdown("### 📥 导入我的岗位表")
    st.caption(f"飞书文档被禁复制？按《{_GUIDE}》操作 —— 浏览器扩展一键导出，"
               f"或 F12 抓包后用项目里的 `解码飞书表格.py` 解成 CSV。")

    if st.session_state.get("wz_parsed"):
        _render_mapping(st.session_state["wz_parsed"])
        if st.button("↩ 换一份重新导入", key="wz_reset"):
            _reset()
            st.rerun()
        return

    chan = st.radio("选一条通道", CHANNELS, horizontal=True, key="wz_chan",
                    label_visibility="collapsed")

    if chan.startswith("①"):
        up = st.file_uploader("选文件（.csv / .xlsx / .txt，采集助手导出的也行）",
                              type=["csv", "xlsx", "xlsm", "txt"], key="wz_file")
        if up is not None:
            res = wz.parse_bytes(up.name, up.getvalue())
            if not _set_parsed(res):
                st.error("没解析出数据行 —— " + ("；".join(res.get("warnings") or ["文件是空的"])))
            else:
                st.rerun()

    elif chan.startswith("②"):
        st.caption("在飞书多维表格 / Excel / WPS 里 **选中表格区域 → Ctrl+C → 粘到下面**。"
                   "复制出来是制表符分隔，有表头更好；没表头也能按内容猜列（第一行不会丢）。")
        txt = st.text_area("粘到这里", height=150, key="wz_paste",
                           placeholder="岗位名称\t公司\t工作城市\t投递链接\n..."
                                       "数据分析工程师\t云南机场集团\t昆明\thttps://...")
        if st.button("🔍 解析", type="primary", key="wz_parse_paste"):
            if not (txt or "").strip():
                st.warning("先粘贴表格内容。")
            else:
                if not _set_parsed(wz.parse_text(txt, source="复制粘贴导入")):
                    st.error("没解析出数据行，检查一下是不是复制空了。")
                else:
                    st.rerun()
        st.caption("💡 更省事：复制完直接双击项目里的 **从剪贴板导入.bat**，连打开网页都省了。")

    elif chan.startswith("③"):
        st.markdown("**飞书多维表格被禁复制/导出时用这条**（成功率最高，纯本地、不联网）")
        st.markdown(
            "1. 浏览器打开那个飞书表，等它**完全加载**\n"
            "2. 按 **F12** → **Network（网络）** 标签 → **F5 刷新**\n"
            "3. 点 **Size** 列**从大到小排序**，逐条点开 **Preview**，"
            "找到能看到岗位记录（公司名/岗位名）的那条\n"
            "4. 右键 → **Copy response**，整串存成 `抓包.txt`"
            "（看到 `H4sI` 开头的一大串 base64 也照样存）\n"
            "5. 在项目文件夹里跑：　`venv\\Scripts\\python.exe 解码飞书表格.py 抓包.txt`\n"
            "6. 会生成 `data\\飞书岗位导出.csv` → 点下面的按钮直接读进来"
        )
        b1, b2 = st.columns([1, 2])
        if b1.button("📂 读取 data/飞书岗位导出.csv", type="primary", key="wz_load_decoded"):
            res = wz.load_decoded_csv()
            if not res.get("ok"):
                st.error(res.get("msg", "还没生成"))
            else:
                st.caption(f"来源：{res['path']}")
                _set_parsed(res)
                st.rerun()
        b2.caption("也可以直接把解码出来的 CSV 用通道 ① 上传，效果一样。")
        with st.expander(f"📖 完整图文步骤（{_GUIDE}）", expanded=False):
            import os
            from . import config
            p = os.path.join(config.PROJECT_ROOT, _GUIDE)
            if os.path.exists(p):
                with open(p, encoding="utf-8") as f:
                    st.markdown(f.read())
            else:
                st.caption("（没找到该指南文件）")

    else:
        st.markdown("**截图 OCR（兜底，100% 能成）**　—— 屏幕上能看到的东西就一定能截下来。")
        st.caption("先用 **Win+Shift+S** 按列截图保存好；通道还在做（RapidOCR 依赖较重），"
                   "现在可以把截图直接发给阿枢，我帮你识别成 CSV 再走通道 ①。")
        st.button("🖼 选择截图（暂未开放）", disabled=True, key="wz_ocr")
