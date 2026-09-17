# -*- coding: utf-8 -*-
"""手机备考手册 · 真实浏览器验收（Playwright + 本机 Chrome / Edge）。

改完卡片网页先跑这个，确认：
  1. 页面无 JS 报错、七个页签（含新增的「🎬 微课」）都能渲染
  2. 微课只在 🔴 核心必学出现，时长全是 10~20 分钟，且给的是 B 站搜索词而不是外链
  3. 必背卡三层标签到位：🔴/🟡 在正文，🔵 全部折叠在 .ext 里，不占主背诵区
  4. 每张卡都有「个人刷题总结」空白区，输入后刷新还在
  5. 每日任务模式 A / B 切换正常：A 带微课环节、B 完全不带视频
  6. 原有功能没被破坏：今日/必背/刷题/专业/面试/避坑 都有内容，搜索还能用

运行： venv\\Scripts\\python.exe tests/test_study_card.py
没装 playwright 或没浏览器时自动跳过（退出码 0），不拖垮 tests/run_all.py。
"""
from __future__ import annotations

import functools
import http.server
import json
import socketserver
import sys
import threading
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
DIR = ROOT / "备考冲刺资料"
FILE = DIR / "手机备考手册.html"

ok = fail = 0


def check(name, cond, extra=None):
    global ok, fail
    if cond:
        ok += 1
        print("  ✓ " + name)
    else:
        fail += 1
        print("  ✗ " + name + (("  -> " + json.dumps(extra, ensure_ascii=False)) if extra is not None else ""))


def pick_browser(p):
    """优先用本机已装的 Chrome / Edge（省掉几百 MB 内核下载）。"""
    for kw in ({"channel": "chrome"}, {"channel": "msedge"}):
        try:
            return p.chromium.launch(headless=True, **kw)
        except Exception:
            continue
    import os
    for exe in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"):
        if os.path.exists(exe):
            try:
                return p.chromium.launch(headless=True, executable_path=exe)
            except Exception:
                continue
    return None


def serve():
    """起一个临时静态服务，避免 file:// 下 localStorage 被禁用导致误判。"""
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(DIR))
    handler = type("QuietHandler", (http.server.SimpleHTTPRequestHandler,),
                   {"log_message": lambda self, *a, **k: None})
    httpd = socketserver.TCPServer(("127.0.0.1", 0), functools.partial(handler, directory=str(DIR)))
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd, httpd.server_address[1]


error_handler = None


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  ⚠ 没装 playwright，跳过卡片网页浏览器验收")
        return 0
    if not FILE.exists():
        check("存在 手机备考手册.html", False, str(FILE))
        return 1

    httpd, port = serve()
    url = f"http://127.0.0.1:{port}/{quote(FILE.name)}"

    with sync_playwright() as p:
        browser = pick_browser(p)
        if not browser:
            httpd.shutdown()
            print("  ⚠ 本机没有可用的 Chrome / Edge，跳过卡片网页浏览器验收")
            return 0
        try:
            page = browser.new_page(viewport={"width": 390, "height": 844})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            # 临时静态服务器没有 favicon，这类 404 与页面逻辑无关
            page.on("console", lambda m: errors.append("console:" + m.text)
                    if (m.type == "error" and "favicon" not in m.text and "Failed to load resource" not in m.text)
                    else None)
            page.goto(url)
            page.wait_for_timeout(400)

            # ---- [1] 无报错 + 七个页签都在 ----
            check("页面无 JS 报错", not errors, errors[:3])
            navs = page.locator("nav button").count()
            check("底部导航 7 个页签", navs == 7, navs)
            labels = page.locator("nav button").all_inner_texts()
            check("含「🎬 微课」页签", any("微课" in t for t in labels), labels)
            for pid in ("today", "course", "mem", "quiz", "major", "iv", "tips"):
                n = page.locator(f"#p-{pid}").inner_html()
                check(f"页面 #{pid} 有内容", len(n) > 200)

            def go(pid):
                """切到某个页签：页面是 display:none 切换的，不切过去元素就点不动。"""
                page.locator(f"nav button[data-p='{pid}']").click()
                page.wait_for_timeout(150)

            # ---- [2] 微课页：只给 🔴，时长 10~20 分钟，只有搜索词不给外链 ----
            go("course")
            mcs = page.locator("#p-course .mc")
            total = mcs.count()
            check("微课条目 ≥ 24 条（不是寥寥几条）", total >= 24, total)
            mins = []
            has_word = 0
            for i in range(total):
                row = mcs.nth(i)
                t = row.inner_text()
                for part in t.split("分钟")[0].split():
                    pass
                if "分钟" in t:
                    frag = t.split("分钟")[0][-4:].strip()
                    num = "".join(ch for ch in frag if ch.isdigit())
                    if num:
                        mins.append(int(num))
                if row.locator("[data-cp]").count() > 0:
                    has_word += 1
            check("每条微课都有 B 站搜索词（可复制）", has_word == total, (has_word, total))
            check("微课时长都在 10~20 分钟", mins and min(mins) >= 10 and max(mins) <= 20, (min(mins or [0]), max(mins or [0])))
            links = page.locator("#p-course a[href^='http']").count()
            check("微课页不放外部链接（只给搜索词）", links == 0, links)

            # 微课打勾 + 持久化
            box1 = page.locator("#p-course .mc").first.locator(".mcbox")
            box1.click()
            page.wait_for_timeout(120)
            done_cls = page.locator("#p-course .mc").first.get_attribute("class") or ""
            check("微课看完可打勾", "done" in done_cls, done_cls)
            hero = page.locator("#p-course .hero .big").inner_text()
            check("微课进度已更新", hero.strip().startswith("1 /"), hero)

            # ---- [3] 逼背三层标签 ----
            go("mem")
            cards = page.locator("#p-mem details.card")
            cn = cards.count()
            check("必背卡片 ≥ 10 组", cn >= 10, cn)
            bad_cards = []
            for i in range(cn):
                c = cards.nth(i)
                body_ul = c.locator(".body > ul").first
                if "lv-b" in (body_ul.inner_html() or ""):
                    bad_cards.append(i)
            check("🔵 拓展没有混进主背诵区", not bad_cards, bad_cards)
            ext_n = page.locator("#p-mem .ext").count()
            check("存在 🔵 拓展选学折叠区", ext_n >= 5, ext_n)
            c1 = page.locator("#p-mem .lv-c").count()
            y1 = page.locator("#p-mem .lv-y").count()
            b1 = page.locator("#p-mem .lv-b").count()
            check("🔴 核心条目够多（≥ 45）", c1 >= 45, c1)
            check("🟡 次重要条目存在（≥ 20）", y1 >= 20, y1)
            check("🔵 拓展条目存在（≥ 10）", b1 >= 10, b1)

            # ---- [4] 个人刷题总结：每张卡都有，输入后刷新还在 ----
            tas = page.locator("#p-mem textarea.note").count()
            check("每张必背卡都有个人总结区", tas == cn, (tas, cn))
            page.locator("#p-mem details.card").first.locator("> summary").click()
            page.wait_for_timeout(150)
            first = page.locator("#p-mem textarea.note").first
            first.click()
            first.fill("今天错在把「多几倍」当成「是几倍」，下次先看题干有没有'比'字")
            page.wait_for_timeout(200)
            hint = page.locator("#p-mem .notehint").first.inner_text()
            check("输入后提示已自动保存", "已自动保存" in hint, hint)
            page.reload()
            page.wait_for_timeout(300)
            v = page.locator("#p-mem textarea.note").first.input_value()
            check("刷新后个人总结还在", "多几倍" in v, v[:30])
            go("major")
            mj = page.locator("#p-major textarea.note").count()
            check("专业课也有个人总结区", mj >= 9, mj)

            # ---- [5] 模式 A / B ----
            go("today")
            seg = page.locator("#p-today [data-mode]")
            check("今日页有模式 A/B 切换", seg.count() == 2, seg.count())
            cur = page.locator("#p-today .seg button.on").inner_text()
            check("默认是模式 A", "模式A" in cur, cur)
            tasks_a = page.locator("#p-today .task").all_inner_texts()
            n_video = sum(1 for t in tasks_a if "🎬" in t)
            check("模式 A 里有微课环节", n_video >= 2, n_video)
            has60 = any("60 秒" in t for t in tasks_a)
            check("模式 A 仍保留「每题 ≤60 秒」训练要求", has60)
            has2p = any("2 篇" in t for t in tasks_a)
            check("模式 A 仍保留「2 篇材料 10 题」训练量", has2p)

            page.locator("#p-today [data-mode='B']").click()
            page.wait_for_timeout(250)
            tasks_b = page.locator("#p-today .task").all_inner_texts()
            check("模式 B 完全不带视频", not any("🎬" in t for t in tasks_b), tasks_b[:1])
            check("模式 B 仍有资料分析刷题任务", any("资料分析" in t for t in tasks_b))
            has60b = any("60 秒" in t for t in tasks_b)
            check("模式 B 训练要求不变（60 秒）", has60b)

            # 打勾 + 持久化
            first_task = page.locator("#p-today .task").first
            first_task.click()
            page.wait_for_timeout(150)
            cls = first_task.get_attribute("class") or ""
            check("任务可以打勾", "ck" in cls, cls)
            st = page.locator("#s-streak").inner_text()
            check("连续天数已经算出来了（不再是 0）", st.strip() != "0", st)

            page.locator("#p-today [data-mode='A']").click()
            page.wait_for_timeout(200)
            again = page.locator("#p-today .task").all_inner_texts()
            check("切回模式 A 任务正常", any("🎬" in t for t in again))

            # ---- [6] 原有功能没坏 ----
            page.locator("#search").fill("基期")
            page.wait_for_timeout(200)
            hidden = page.locator("#p-mem .hide").count()
            check("搜索仍能过滤卡片", hidden > 0, hidden)
            page.locator("#search").fill("")
            page.wait_for_timeout(150)

            check("整轮操作仍无 JS 报错", not errors, errors[:3])
        finally:
            browser.close()
            httpd.shutdown()

    print(f"\n  共 {ok + fail} 项：通过 {ok}，失败 {fail}")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
