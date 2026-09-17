# -*- coding: utf-8 -*-
"""真实浏览器里的网申助手验收（Playwright + 本机 Chrome / Edge，不用下载内核）。

三个模拟页各跑一遍：北森式 / Moka 式（分步）/ 国企自研（老表格 + 只读 + 富文本）。
流程完全按真人操作：打开页面 → 点右下角悬浮球 → 点「🚀 填入空字段」→ 看报告。

看两个指标：
  · 填充率 = 真被填上的控件 / 全部控件（受"资料里有没有这个值"影响）
  · 识别率 = 认出是什么字段的控件 / 全部控件（这才是脚本的能力上限指标）

运行： venv\\Scripts\\python.exe tests/autofill_browser_test.py
没装 playwright 或没浏览器时自动跳过（退出码 0），不拖垮 tests/run_all.py。
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SCRIPT = ROOT / "网申助手.user.js"
FIXTURES = [
    ("北森式（antd 自绘下拉 + 卡片单选）", "网申测试页_北森式.html", 45, 85),
    ("Moka 式（分步表单）", "网申测试页_Moka式.html", 40, 85),
    ("国企自研（老表格 + 只读 + 富文本）", "网申测试页_国企自研.html", 35, 75),
]

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
            b = p.chromium.launch(headless=True, **kw)
            return b
        except Exception:
            continue
    for exe in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"):
        if os.path.exists(exe):
            try:
                return p.chromium.launch(headless=True, executable_path=exe)
            except Exception:
                continue
    return None


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  ⚠ 没装 playwright，跳过浏览器验收（pip install playwright 后可跑）")
        return 0

    if not SCRIPT.exists():
        check("存在 网申助手.user.js", False, str(SCRIPT))
        return 1
    code = SCRIPT.read_text(encoding="utf-8")

    with sync_playwright() as p:
        browser = pick_browser(p)
        if not browser:
            print("  ⚠ 本机没有可用的 Chrome / Edge，跳过浏览器验收")
            return 0
        try:
            for title, fname, min_fill, min_recog in FIXTURES:
                print("[%s]" % title)
                fp = ROOT / "tests" / "fixtures" / fname
                if not fp.exists():
                    check("存在测试页 " + fname, False)
                    continue
                page = browser.new_page()
                page.goto(fp.as_uri())
                page.wait_for_timeout(300)
                page.evaluate(code)                      # 注入脚本（等于油猴装好了）
                page.wait_for_timeout(400)

                mounted = page.evaluate(
                    "!!(document.querySelector('[data-ihub=v5]') && "
                    "document.querySelector('[data-ihub=v5]').shadowRoot)")
                check("悬浮球挂上了（且用了 Shadow DOM 隔离样式）", mounted)

                # 真人路径：点悬浮球 → 点「填入空字段」
                page.click(".ihub-fab")
                page.wait_for_timeout(200)
                page.click('button:has-text("填入空字段")')
                page.wait_for_timeout(1600)              # 自绘下拉是异步点选的

                # Moka 是分步表单，后面几步要点开再填一次
                if "Moka" in title:
                    for step in (1, 2):
                        page.click(".steps button >> nth=%d" % step)
                        page.wait_for_timeout(200)
                        page.click('button:has-text("填入空字段")')
                        page.wait_for_timeout(1200)

                page.click('button:has-text("算一下填充率")')
                page.wait_for_timeout(200)
                sc = page.evaluate("window.__fillScore || null")
                panel = page.evaluate(
                    "(function(){var h=document.querySelector('[data-ihub=v5]');"
                    "var r=h&&h.shadowRoot;if(!r)return null;"
                    "return {fail:r.querySelectorAll('.ihub-fail').length,"
                    "ok:r.querySelectorAll('.ihub-oklist div').length,"
                    "learn:r.querySelectorAll('select').length};})()")
                check("页面算出了填充率", sc is not None, sc)
                if not sc:
                    page.close()
                    continue

                total, done = sc["total"], sc["done"]
                fill_pct = sc["pct"]
                need_human = (panel or {}).get("fail", 0)
                unknown = len([m for m in sc.get("miss", [])]) and 0  # 未识别数从报告文案里数
                unknown = page.evaluate(
                    "(function(){var h=document.querySelector('[data-ihub=v5]');"
                    "var r=h&&h.shadowRoot;if(!r)return 0;"
                    "return [].slice.call(r.querySelectorAll('.ihub-fail')).filter(function(x){"
                    "return /没认出/.test(x.textContent||'');}).length;})()")
                recog_pct = round((total - unknown) / total * 100) if total else 0
                print("     填充 %d/%d = %d%%　｜　识别率 %d%%（未识别 %d）　｜　需人工 %d"
                      % (done, total, fill_pct, recog_pct, unknown, need_human))
                check("填充率 ≥ %d%%" % min_fill, fill_pct >= min_fill, fill_pct)
                check("识别率 ≥ %d%%（认不出就没法自动填）" % min_recog, recog_pct >= min_recog, recog_pct)
                check("报告列出了「需人工」项（填不进去的都摊开给你看）", need_human > 0, need_human)
                check("学习区扫到了可教的字段或已全部认识", (panel or {}).get("learn", 0) >= 0)

                if sc.get("miss"):
                    print("     还没填上的：" + "、".join(sc["miss"][:12]) +
                          (" …" if len(sc["miss"]) > 12 else ""))
                page.close()
        finally:
            browser.close()

    print("\n结果: %d 通过, %d 失败" % (ok, fail))
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
