# -*- coding: utf-8 -*-
"""页面采集助手：在你**已登录**的浏览器里，把当前页面的岗位导出 CSV（再导入 InternHub）。

支持三种页面：
1. 岗位卡片列表（国聘/BOSS/智联/牛客/高校就业网等）
2. 标准 HTML 表格（学校就业网公布的岗位表、Excel 转网页等）
3. 飞书/钉钉多维表格（在线共享表，自动滚动加载全部行）

合规要点：完全由你手动点击触发；只读取当前页面**已渲染**的内容；
不登录、不提交、不绕过验证码、不调用平台私有接口。
"""
import os

from . import config


def build_js() -> str:
    return r"""// ==UserScript==
// @name         采集助手（InternHub·本地本人使用）
// @namespace    internhub.local
// @version      2.0
// @description  在已登录的浏览器里，把当前页面的岗位（含网页表格 / 飞书多维表格）导出 CSV，再导入 InternHub
// @match        *://*/*
// @grant        none
// ==/UserScript==
(function () {
  'use strict';

  const JOB_WORDS = /招聘|校招|实习|岗位|工程师|专员|经理|助理|顾问|设计|运营|研发|测试|开发|销售|管培|技术|管理/;
  const SKIP = /登录|注册|首页|关于|帮助|更多|下一页|上一页|隐私|协议|岗位职责|任职要求|返回顶部/;

  const HEAD_KEYS = {
    title:    /^(岗位|职位|岗位名称|职位名称|招聘岗位|招聘职位|职位名|名称|岗位\/职位|拟聘岗位)$/,
    company:  /(公司|单位|企业|用人单位|招聘单位|机构|集团)/,
    city:     /(城市|地点|工作地|工作地点|地区|所在地|省份|区域)/,
    salary:   /(薪资|薪酬|月薪|年薪|工资|待遇)/,
    degree:   /(学历|学位|要求学历)/,
    link:     /(链接|网址|报名|投递|详情|公告|原文|招聘网址|申请)/,
    deadline: /(截止|截 止|报名时间|有效期|结束时间|deadline)/,
    tags:     /(标签|专业|要求|备注|类别|方向|职能)/,
    jobType:  /(岗位类型|招聘类型|性质|批次|类型)/,
    batch:    /(届|年份|毕业时间|届别)/
  };

  function clean(s) { return (s || '').replace(/\s+/g, ' ').trim(); }
  function norm(s) { return clean(s).replace(/[\s*＊:：]/g, ''); }

  const CITIES = ['潍坊','济南','青岛','烟台','威海','昆明','大理','曲靖','玉溪','丽江','保山','昭通','红河','文山','楚雄',
    '北京','上海','深圳','广州','成都','杭州','南京','武汉','西安','重庆','天津','长沙','郑州','合肥','福州','厦门','南昌','贵阳','南宁','兰州'];

  function guessCity(t) {
    for (const c of CITIES) if ((t || '').includes(c)) return c;
    return '';
  }

  function host() { return location.hostname.replace(/^www\./, ''); }

  /* ---------------- 通用表格（HTML table / 飞书多维表格） ---------------- */

  function scrollableAncestors(el) {
    const out = [];
    let n = el;
    while (n && n !== document.body) {
      const st = getComputedStyle(n);
      if (/(auto|scroll)/.test(st.overflowY) && n.scrollHeight > n.clientHeight + 20) out.push(n);
      n = n.parentElement;
    }
    return out;
  }

  async function autoScrollAll() {
    // 虚拟滚动表格（飞书多维表格）默认只渲染可视区，需要先滚动把数据加载满
    const boxes = [];
    document.querySelectorAll('div').forEach(d => {
      const st = getComputedStyle(d);
      if (/(auto|scroll)/.test(st.overflowY) && d.scrollHeight > d.clientHeight + 60 && d.clientHeight > 200) boxes.push(d);
    });
    for (const box of boxes.slice(0, 3)) {
      let last = -1, guard = 0;
      while (guard++ < 120 && box.scrollHeight !== last) {
        last = box.scrollHeight;
        box.scrollTop = box.scrollHeight;
        await new Promise(r => setTimeout(r, 220));
      }
    }
    await new Promise(r => setTimeout(r, 400));
  }

  function cellText(cell) {
    const a = cell.querySelector && cell.querySelector('a[href^="http"]');
    let url = '';
    if (a) url = a.href;
    let text = clean(cell.innerText || cell.textContent || '');
    if (!url) {
      const m = text.match(/https?:\/\/[^\s，,；;）)]+/);
      if (m) url = m[0];
    }
    return { text: text, url: url };
  }

  // 把表格网格解析成 {headers:[], rows:[[{text,url}]]}
  function readGrid() {
    // 1) 标准 <table>
    const tables = Array.from(document.querySelectorAll('table')).filter(t => t.rows && t.rows.length >= 2);
    if (tables.length) {
      let best = tables[0], bestScore = -1;
      for (const t of tables) {
        const head = t.rows[0];
        if (!head) continue;
        const cols = head.cells.length;
        const score = (t.rows.length - 1) * Math.max(cols, 1);
        if (cols >= 2 && cols <= 30 && score > bestScore) { best = t; bestScore = score; }
      }
      const rows = [];
      const headers = Array.from(best.rows[0].cells).map(c => clean(c.innerText || c.textContent));
      for (let i = 1; i < best.rows.length; i++) {
        const r = best.rows[i];
        if (!r.cells || !r.cells.length) continue;
        rows.push(Array.from(r.cells).map(cellText));
      }
      if (rows.length) return { headers: headers, rows: rows };
    }

    // 2) 多维表格网格（飞书 bitable / 通用 role=grid）
    const grids = document.querySelectorAll('[role="grid"], .bitable-table, .grid-view, [class*="bitable"]');
    for (const g of grids) {
      const rowEls = g.querySelectorAll('[role="row"], tr, [class*="row-wrapper"]');
      const parsed = [];
      const headerSet = [];
      rowEls.forEach((r, idx) => {
        const cells = r.querySelectorAll('[role="gridcell"], [role="columnheader"], td, [class*="cell"]');
        if (cells.length < 2) return;
        const vals = Array.from(cells).map(cellText);
        if (idx === 0 || r.querySelector('[role="columnheader"]')) {
          if (!headerSet.length) vals.forEach(v => headerSet.push(v.text));
          return;
        }
        if (vals.some(v => v.text)) parsed.push(vals);
      });
      if (parsed.length >= 2) {
        return { headers: headerSet, rows: parsed };
      }
    }
    return null;
  }

  function mapHeaders(headers, sample) {
    const map = {};
    headers.forEach((h, i) => {
      const n = norm(h);
      if (!n) return;
      for (const key in HEAD_KEYS) {
        if (map[key] === undefined && HEAD_KEYS[key].test(n)) { map[key] = i; break; }
      }
    });
    // 兜底：没识别出岗位列时，挑“最长文本”的列当岗位名
    if (map.title === undefined && sample && sample.length) {
      const cols = Math.max.apply(null, sample.map(r => r.length));
      let bestCol = 0, bestLen = -1;
      for (let c = 0; c < cols; c++) {
        if (c === map.company || c === map.city) continue;
        const avg = sample.slice(0, 30).reduce((s, r) => s + ((r[c] && r[c].text) ? r[c].text.length : 0), 0) / Math.min(sample.length, 30);
        if (avg > bestLen && avg >= 4) { bestLen = avg; bestCol = c; }
      }
      map.title = bestCol;
    }
    return map;
  }

  function rowsFromGrid(grid) {
    const { headers, rows } = grid;
    const sample = rows.slice(0, 40);
    const map = mapHeaders(headers, sample);
    const out = [];
    const seen = new Set();
    rows.forEach(r => {
      const get = (k) => (map[k] !== undefined && r[map[k]]) ? r[map[k]].text : '';
      const title = get('title');
      if (!title || title.length < 2) return;
      const key = title + '|' + get('company');
      if (seen.has(key)) return;
      seen.add(key);
      // 链接：优先“链接”列；否则扫整行第一个 http
      let link = '';
      if (map.link !== undefined && r[map.link]) link = r[map.link].url || '';
      if (!link) {
        for (const c of r) { if (c && c.url) { link = c.url; break; } }
      }
      if (!link) link = location.href;   /* 整表同源：至少指回原页面 */
      // 未识别的列全部塞进描述，避免丢信息
      const known = new Set(Object.keys(map).map(k => map[k]));
      const extra = [];
      r.forEach((c, i) => {
        if (known.has(i) || !c || !c.text) return;
        const hn = headers[i] ? headers[i] : ('第' + (i + 1) + '列');
        extra.push(hn + '：' + c.text);
      });
      out.push({
        title: title,
        company: get('company'),
        city: get('city') || guessCity(title + ' ' + extra.join(' ')),
        salary: get('salary'),
        degree: get('degree'),
        tags: get('tags'),
        jobType: get('jobType'),
        batch: get('batch'),
        deadline: get('deadline'),
        link: link,
        text: extra.join(' | ').slice(0, 400)
      });
    });
    return out;
  }

  /* ---------------- 岗位卡片 ---------------- */

  function rowsFromCards() {
    const rows = [];
    const seen = new Set();
    const pushFromEl = (el) => {
      const a = el.querySelector && el.querySelector('a[href]');
      if (!a) return;
      const title = clean(a.getAttribute('title') || a.innerText || '');
      const href = a.href || '';
      if (!title || title.length < 6 || SKIP.test(title) || !JOB_WORDS.test(title)) return;
      if (!/^https?:/.test(href)) return;
      if (seen.has(href)) return;
      const text = clean(el.innerText || '').slice(0, 220);
      let company = '';
      const lines = (el.innerText || '').split('\n').map(clean).filter(Boolean);
      for (const ln of lines) {
        if (ln !== title && ln.length >= 4 && ln.length <= 30 && !JOB_WORDS.test(ln)) { company = ln; break; }
      }
      if (!company) {
        for (const ln of lines) { if (ln !== title && ln.length >= 4 && ln.length <= 30) { company = ln; break; } }
      }
      seen.add(href);
      rows.push({ title: title, company: company, city: guessCity(text) || guessCity(title), link: href, text: text });
    };
    const blocks = document.querySelectorAll('li, .job, .job-item, .position, .list-item, tr, .card, article');
    if (blocks.length) blocks.forEach(pushFromEl);
    if (rows.length < 5) document.querySelectorAll('a[href]').forEach(pushFromEl);
    return rows;
  }

  /* ---------------- CSV ---------------- */

  const HEAD = ['岗位', '公司', '城市', '学历', '标签', '链接', '截止日期', '描述', '岗位类型', '届别', '来源', '薪资'];

  function csv(rows) {
    const h = host();
    const lines = [HEAD.join(',')];
    for (const r of rows) {
      const cells = [r.title, r.company, r.city, r.degree || '', r.tags || '', r.link, r.deadline || '',
                     r.text || '', r.jobType || '秋招', r.batch || '2027届', h, r.salary || ''];
      lines.push(cells.map(v => '"' + String(v === undefined || v === null ? '' : v).replace(/"/g, '""') + '"').join(','));
    }
    return '\ufeff' + lines.join('\r\n');
  }

  function download(rows) {
    const blob = new Blob([csv(rows)], { type: 'text/csv;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = '岗位采集_' + host() + '_' + new Date().toISOString().slice(0, 10) + '.csv';
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 3000);
  }

  /* ---------------- 入口 ---------------- */

  let busy = false;
  let btn = null;
  function setStatus(t) { if (btn) btn.textContent = t; }
  async function onClick() {
    if (busy) return;
    busy = true;
    try {
      setStatus('⏳ 正在加载全部行…');
      const grid0 = readGrid();
      // 表格页先尝试自动滚动（虚拟滚动只渲染可见行）
      if (!grid0 || grid0.rows.length < 50) {
        try { await autoScrollAll(); } catch (e) { /* ignore */ }
      }
      setStatus('⏳ 正在解析…');
      const grid = readGrid();
      const rows = (grid && grid.rows.length >= 2) ? rowsFromGrid(grid) : rowsFromCards();
      if (!rows.length) {
        alert('没识别到数据。\n\n建议：\n1) 先滚动页面把内容加载出来\n2) 表格页请确认表头在第一行\n3) 卡片页请确认岗位标题已渲染');
        return;
      }
      const mode = (grid && grid.rows.length >= 2) ? '网页表格' : '岗位卡片';
      if (confirm('识别方式：' + mode + '\n共 ' + rows.length + ' 条\n\n导出 CSV？\n（导出后在 InternHub「📥 导入」里一键入库）')) download(rows);
    } finally {
      setStatus('📥 采集本页岗位');
      busy = false;
    }
  }

  // __BOOKMARK_CUT__ 书签版从这里截断（书签版不需要悬浮按钮）
  btn = document.createElement('button');
  btn.textContent = '📥 采集本页岗位';
  btn.style.cssText = 'position:fixed;right:18px;bottom:72px;z-index:999999;padding:10px 14px;' +
    'background:#0a6cb0;color:#fff;border:none;border-radius:8px;cursor:pointer;font-size:14px;' +
    'box-shadow:0 2px 8px rgba(0,0,0,.25)';
  btn.onclick = onClick;
  window.addEventListener('load', () => document.body.appendChild(btn));

  // 调试/自测入口（本地脚本，不影响功能）
  window.__IHUB_COLLECTOR__ = { readGrid: readGrid, rowsFromGrid: rowsFromGrid,
    mapHeaders: mapHeaders, csv: csv, rowsFromCards: rowsFromCards, collect: onClick };
})();
"""


def save_userscript(path: str = None) -> str:
    path = path or os.path.join(config.PROJECT_ROOT, "采集助手.user.js")
    with open(path, "w", encoding="utf-8") as f:
        f.write(build_js())
    return path


_BOOKMARK_HEAD = "javascript:"
_BOOKMARK_TAIL = "onClick();})()"


def _minify(js: str) -> str:
    """去掉整行注释与缩进，压成一行。

    关键坑：压行后 JS 的"自动分号插入(ASI)"会失效——
    上一行以 `)`/`}`/标识符结尾、下一行以 `(`/`[`/`+`/`-` 开头时，
    两行会被连成一次函数调用/下标访问，直接语法报错。这里检测并补分号。
    """
    lines = []
    for line in js.split("\n"):
        s = line.strip()
        if not s or s.startswith("//"):
            continue
        lines.append(s)

    out = []
    for i, s in enumerate(lines):
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        if nxt[:1] in ("(", "[", "+", "-") and not s.endswith(
                (";", "{", "}", ",", "(", "[", ":", "=", "=>", "&&", "||", "?", "+", "-", "*", "/")):
            s += ";"
        out.append(s)

    text = " ".join(out)
    while "  " in text:
        text = text.replace("  ", " ")
    return text


def build_bookmarklet() -> str:
    """从同一份源码生成书签版（免装扩展）：点书签即采集当前页并导出 CSV。"""
    js = build_js()
    # 去掉 UserScript 头
    idx = js.find("(function () {")
    body = js[idx:]
    # 在哨兵处截断（书签版不需要悬浮按钮与调试钩子），再补上自动执行
    sentinel = "// __BOOKMARK_CUT__"
    cut = body.find(sentinel)
    if cut < 0:
        raise RuntimeError("采集脚本缺少 __BOOKMARK_CUT__ 哨兵，无法生成书签版")
    body = body[:cut]
    body = _minify(body)
    assert "\n" not in body
    # 压成一行后，任何"整行 // 注释"都会吞掉后面的代码；只允许 URL 里的 ://
    for i in range(len(body) - 1):
        if body[i:i + 2] == "//" and (i == 0 or body[i - 1] != ":"):
            raise RuntimeError(
                f"书签版源码里有会吞代码的 // 注释（位置 {i}）：{body[max(0, i - 60):i + 60]!r}")
    return _BOOKMARK_HEAD + body + "onClick();" + _BOOKMARK_TAIL


def save_bookmarklet(path: str = None) -> str:
    path = path or os.path.join(config.PROJECT_ROOT, "采集书签.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(build_bookmarklet() + "\n")
    return path


if __name__ == "__main__":
    print(save_userscript())
    print(save_bookmarklet())

