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
import re

from . import config


def build_js() -> str:
    return r"""// ==UserScript==
// @name         采集助手（InternHub·本地本人使用）
// @namespace    internhub.local
// @version      2.1
// @description  在已登录的浏览器里，把当前页面的岗位（含网页表格 / 飞书多维表格）导出 CSV，再导入 InternHub
// @match        *://*/*
// @match        file:///*
// @grant        GM_info
// ==/UserScript==
// 注意：故意声明 GM_info（而不是 @grant none）——@grant none 会以"页面脚本"注入，
// 政府/国企网站的严格 CSP 会把它拦掉（表现：页面上没有按钮）。声明任一 GM_* 后
// Tampermonkey 会在自己的沙箱里执行，不受页面 CSP 影响。
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

  /* ---------------- 通用表格（HTML table / 飞书多维表格 / 任意"重复行"结构） ---------------- */

    var SCROLL_BUDGET_MS = 9000;  /* 自动滚动总预算：宁可少抓几行，也不能让用户干等 */
  var SCROLL_STEP_MS = 140;

    function countRows() {  /* 当前已渲染的"疑似数据行"数量（用于判断是否还在加载） */
    var n = document.querySelectorAll('[role="row"], tr, [data-row-index], [class*="row-wrapper"], [class*="grid-row"]').length;
    return n;
  }

  async function autoScrollAll() {
    // 虚拟滚动表格（飞书多维表格等）只渲染可视区，先滚动把数据加载出来；有总时间上限
    var boxes = [];
    document.querySelectorAll('div').forEach(function (d) {
      var st = getComputedStyle(d);
      if (/(auto|scroll)/.test(st.overflowY) && d.scrollHeight > d.clientHeight + 60 && d.clientHeight > 200) boxes.push(d);
    });
    var deadline = Date.now() + SCROLL_BUDGET_MS;
    for (var b = 0; b < Math.min(boxes.length, 3); b++) {
      var box = boxes[b], lastCount = -1, stall = 0;
      while (Date.now() < deadline && stall < 4) {
        var before = countRows();
        box.scrollTop = box.scrollTop + Math.max(box.clientHeight * 0.9, 200);
        await new Promise(function (r) { setTimeout(r, SCROLL_STEP_MS); });
        var after = countRows();
        if (after <= before && after === lastCount) { stall++; } else { stall = 0; }
        lastCount = after;
                if (box.scrollTop + box.clientHeight >= box.scrollHeight - 4) {  /* 到底了，回头再滚一遍把没加载的补齐 */
          await new Promise(function (r) { setTimeout(r, 250); });
          box.scrollTop = 0;
          await new Promise(function (r) { setTimeout(r, SCROLL_STEP_MS); });
        }
      }
    }
    await new Promise(function (r) { setTimeout(r, 300); });
  }

  function cellText(cell) {
    var a = cell.querySelector && cell.querySelector('a[href^="http"]');
    var url = '';
    if (a) url = a.href;
    var text = clean(cell.innerText || cell.textContent || '');
    if (!url) {
      var m = text.match(/https?:\/\/[^\s，,；;）)]+/);
      if (m) url = m[0];
    }
    return { text: text, url: url };
  }

  /* --- 通用兜底：不依赖 class 名，靠"重复行"结构找表格 --- */
  function textLeafCount(el) {
    if (!el || !el.querySelectorAll) return 0;
    var leaves = el.querySelectorAll('*'), n = 0;
    for (var i = 0; i < leaves.length; i++) {
      if (leaves[i].children && leaves[i].children.length === 0) {
        if (clean(leaves[i].textContent)) n++;
      }
    }
    if (n === 0 && clean(el.textContent)) n = 1;
    return n;
  }
  function mostCommon(arr) {
    var m = {}, best = 0, bestN = 0;
    arr.forEach(function (v) { m[v] = (m[v] || 0) + 1; if (m[v] > bestN) { bestN = m[v]; best = v; } });
    return Number(best);
  }
  function rowCells(rowEl) {
    // 一行的"单元格"= 直接子元素里有文字的；子元素太少则再往下一层找
    var kids = Array.prototype.slice.call(rowEl.children || []);
    var cells = kids.filter(function (k) { return textLeafCount(k) > 0; });
    if (cells.length >= 2) return cells;
    var deeper = [];
    kids.forEach(function (k) {
      Array.prototype.slice.call(k.children || []).forEach(function (kk) {
        if (textLeafCount(kk) > 0) deeper.push(kk);
      });
    });
    return deeper.length >= 2 ? deeper : cells;
  }
  function detectGridsHeuristic() {
    var cands = [];
    var boxes = document.querySelectorAll('div,ul,ol,tbody,section,main');
    for (var i = 0; i < boxes.length; i++) {
      var box = boxes[i];
      var kids = Array.prototype.slice.call(box.children || []);
      if (kids.length < 3 || kids.length > 400) continue;
      var counts = kids.map(textLeafCount);
      var nonEmpty = counts.filter(function (c) { return c > 0; });
            if (nonEmpty.length / kids.length < 0.85) continue;  /* 大多数孩子都得有文字 */
      var mode = mostCommon(nonEmpty);
            if (mode < 2) continue;  /* 至少 2 列 */
      var rowEls = kids.filter(function (k) { return Math.abs(textLeafCount(k) - mode) <= 1; });
      if (rowEls.length < 3) continue;
      // 每行都得能切出 >=2 个格子，否则不是表格
      var ok = 0;
      for (var r = 0; r < Math.min(rowEls.length, 8); r++) if (rowCells(rowEls[r]).length >= 2) ok++;
      if (ok < Math.min(rowEls.length, 8) * 0.8) continue;
      cands.push({ rows: rowEls, cols: mode, score: rowEls.length * mode, box: box });
    }
    cands.sort(function (a, b) { return b.score - a.score; });
    return cands;
  }

  function looksLikeHeader(cells) {
    var H = /^[^0-9]{0,8}(日期|时间|公司|单位|企业|岗位|职位|城市|地点|地区|学历|届|类型|备注|专业|行业|薪资|待遇|链接|网址|要求|状态|编号|序号|名称|性质|批次|是否|领域|方向|文档|投递|招聘)/;
    var hit = 0, short = 0;
    cells.forEach(function (c) {
      var t = clean(c.innerText || c.textContent);
      if (!t || t.length <= 10) short++;
      if (H.test(t)) hit++;
    });
    return hit >= 2 || (hit >= 1 && short === cells.length);
  }

  function gridFromRows(rowEls, headerEls) {
    var headers = headerEls ? rowCells(headerEls).map(function (c) { return clean(c.innerText || c.textContent); }) : [];
    var body = rowEls.filter(function (r) { return r !== headerEls; });   // 表头不再当数据行
    var rows = [];
    body.forEach(function (r) {
      var cells = rowCells(r).map(cellText);
      if (cells.length < 2) return;
      if (!cells.some(function (c) { return c.text; })) return;
      rows.push(cells);
    });
    if (headers.length && rows.length && headers.length !== rows[0].length) {
      // 表头列数和数据列数对不上（常见于前面多了一列勾选框）：按"去掉空表头"重算
      var h2 = headers.filter(function (h) { return clean(h); });
      headers = h2.length === rows[0].length ? h2 : headers;
    }
    return { headers: headers, rows: rows };
  }

  // 把表格网格解析成 {headers:[], rows:[[{text,url}]], mode:'...'}；都失败返回 null
  function readGrid() {
    // 1) 标准 <table>（优先，最靠谱）
    var tables = Array.prototype.slice.call(document.querySelectorAll('table')).filter(function (t) {
      return t.rows && t.rows.length >= 2;
    });
    var bestT = null, bestScore = -1;
    tables.forEach(function (t) {
      var head = t.rows[0];
      if (!head) return;
      var cols = head.cells.length;
      if (cols < 2 || cols > 40) return;
      var score = (t.rows.length - 1) * cols;
      if (score > bestScore) { bestT = t; bestScore = score; }
    });
    if (bestT) {
      var tRows = [];
      var tHeaders = Array.prototype.slice.call(bestT.rows[0].cells).map(function (c) { return clean(c.innerText || c.textContent); });
      for (var i = 1; i < bestT.rows.length; i++) {
        var r = bestT.rows[i];
        if (!r.cells || !r.cells.length) continue;
        tRows.push(Array.prototype.slice.call(r.cells).map(cellText));
      }
      if (tRows.length >= 1 && tHeaders.filter(function (h) { return h; }).length >= 2) {
        return { headers: tHeaders, rows: tRows, mode: '网页表格(table)' };
      }
    }

    // 2) 显式选择器（飞书 bitable / ARIA grid / 常见表格组件）
    var grids = document.querySelectorAll(
      '[role="grid"], [role="table"], .bitable-table, .grid-view, [class*="bitable"], [class*="sheet-grid"], [class*="GridTable"]');
    for (var gi = 0; gi < grids.length; gi++) {
      var g = grids[gi];
      var rowEls = Array.prototype.slice.call(
        g.querySelectorAll('[role="row"], tr, [class*="row-wrapper"], [data-row-index]'));
      var dataRows = [];
      var headerRow = null;
      rowEls.forEach(function (rr) {
        var cells = rr.querySelectorAll('[role="gridcell"], [role="columnheader"], td, th, [class*="cell"]');
        if (cells.length < 2) return;
        if (!headerRow && rr.querySelector('[role="columnheader"], th')) headerRow = rr;
        dataRows.push(rr);
      });
      if (headerRow) dataRows = dataRows.filter(function (x) { return x !== headerRow; });
      if (dataRows.length >= 1) {
        var gg = gridFromRows(dataRows, headerRow);
        if (gg.rows.length >= 1) { gg.mode = '多维表格(选择器)'; return gg; }
      }
    }

    // 3) 通用兜底：靠"重复行"结构（不依赖任何 class 名）
    var cands = detectGridsHeuristic();
    for (var ci = 0; ci < cands.length; ci++) {
      var c = cands[ci];
      var rowEls2 = c.rows.slice();
      var headEl = null;
      var boxFirst = c.box.children && c.box.children[0];
      if (rowEls2.length >= 2) {
        var cand0 = rowEls2[0];
        // 第一个匹配行既是容器的第一个孩子、或长得像表头 → 当表头
        if (cand0 === boxFirst || looksLikeHeader(rowCells(cand0))) headEl = cand0;
      }
      // 容器第一个孩子不是匹配行但也能切出 >=2 格 → 它才是表头
      if (!headEl && boxFirst && rowEls2.indexOf(boxFirst) < 0 && rowCells(boxFirst).length >= 2) headEl = boxFirst;
      var g2 = gridFromRows(rowEls2, headEl);
      if (g2.rows.length >= 2 || (g2.rows.length >= 1 && g2.headers.filter(function (x) { return clean(x); }).length >= 2)) {
        g2.mode = '重复行结构(兜底)';
        return g2;
      }
    }
    return null;
  }

  /* --- 🐞 结构诊断：把页面上"像表格"的结构导出成 txt，发我就能精确定位 --- */
  function diagnose() {
    var lines = [];
    lines.push('URL: ' + location.href);
    lines.push('title: ' + document.title);
    lines.push('已渲染疑似行数: ' + countRows());
    lines.push('');
    lines.push('== 显式选择器命中 ==');
    ['[role="grid"]', '[role="row"]', '[role="gridcell"]', '[role="columnheader"]',
     '.bitable-table', '[class*="bitable"]', '[class*="grid"]', '[data-row-index]', 'table', 'tr'
    ].forEach(function (sel) {
      var n = 0;
      try { n = document.querySelectorAll(sel).length; } catch (e) {}
      lines.push('  ' + sel + ' -> ' + n);
    });
    var gg = readGrid();
    lines.push('');
    lines.push('== readGrid 结果 == ' + (gg ? (gg.mode + ' 行=' + gg.rows.length + ' 列=' + gg.rows[0].length) : '未识别到'));
    if (gg) {
      lines.push('  表头: ' + JSON.stringify(gg.headers));
      lines.push('  第一行: ' + JSON.stringify(gg.rows[0].map(function (x) { return x.text; })));
    }
    lines.push('');
    lines.push('== 候选"重复行"容器（前 8 个）==' );
    var cands = detectGridsHeuristic();
    if (!cands.length) lines.push('  （无）');
    cands.slice(0, 8).forEach(function (c, i) {
      lines.push('  #' + (i + 1) + ' <' + c.box.tagName.toLowerCase() + ' class="' + String(c.box.className || '').slice(0, 120) +
        '"> 行数=' + c.rows.length + ' 列数=' + c.cols);
      lines.push('     首行格子: ' + JSON.stringify(rowCells(c.rows[0]).map(function (x) { return clean(x.innerText).slice(0, 24); })));
    });
    lines.push('');
    lines.push('== 含文字最多的 div（前 6 个，看是不是 canvas 渲染）==');
    var divs = Array.prototype.slice.call(document.querySelectorAll('div'));
    divs.sort(function (a, b) { return clean(b.innerText || '').length - clean(a.innerText || '').length; });
    divs.slice(0, 6).forEach(function (d) {
      lines.push('  <div class="' + String(d.className || '').slice(0, 100) + '"> 字数=' + clean(d.innerText || '').length +
        ' 子元素=' + (d.children ? d.children.length : 0));
    });
    lines.push('');
    lines.push('canvas 数量: ' + document.querySelectorAll('canvas').length +
      '（如果 >0 且上面没有候选行，说明表格是 canvas 画的，DOM 抓不到，只能用"复制粘贴导入"）');
    var blob = new Blob([lines.join('\n')], { type: 'text/plain;charset=utf-8' });
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = '结构诊断_' + host() + '_' + new Date().toISOString().slice(0, 10) + '.txt';
    a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 3000);
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
    // 模糊一轮：表头写成"可投岗位/招聘岗位/岗位信息"这类也要认出来
    if (map.title === undefined) {
      const TITLE_FUZZY = /(岗位|职位|职务)/;
      for (let i = 0; i < headers.length; i++) {
        if (TITLE_FUZZY.test(norm(headers[i]))) { map.title = i; break; }
      }
    }
    if (map.location === undefined) {
      for (let i = 0; i < headers.length; i++) {
        if (/(省市|地点|区域|工作地)/.test(norm(headers[i]))) { map.city = i; break; }
      }
    }
    // 还是没识别出岗位列 → 挑“最长文本”的列当岗位名
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
  let btn = null, diagBtn = null;
  function setStatus(t) { if (btn) btn.textContent = t; }

  async function collectOnce(doScroll) {
    if (doScroll) {
      setStatus('⏳ 正在滚动加载（最多 9 秒）…');
      try { await autoScrollAll(); } catch (e) { /* ignore */ }
    }
    setStatus('⏳ 正在解析…');
    const grid = readGrid();
    const rows = (grid && grid.rows.length >= 1) ? rowsFromGrid(grid) : rowsFromCards();
    return { grid: grid, rows: rows };
  }

  async function onClick() {
    if (busy) return;
    busy = true;
    try {
      // 第一次：如果还没滚动过，先滚动；滚完还读不到，再用卡片方式兜底
      let first = await collectOnce(countRows() < 40);
      if (!first.rows.length) {
        const second = await collectOnce(true);
        if (second.rows.length) first = second;
      }
      if (!first.rows.length) {
        alert('没识别到数据。\n\n' +
          '① 如果这是飞书/钉钉多维表格：请先在表里用「筛选」把范围缩小（例如只在云南、2027届），\n' +
          '   行数太多（几千上万行）时网页只会渲染一小部分，抓不全。\n' +
          '② 更稳的办法：在表格里选中区域 → Ctrl+C → 到 InternHub「📚 备考方案」页用「📋 直接粘贴导入」。\n' +
          '③ 想让我精确定位这个网站：点右下角「🐞 结构诊断」，把下载的 txt 发我。');
        return;
      }
      const mode = first.grid ? first.grid.mode : '岗位卡片';
      const note = (first.grid && first.grid.mode.indexOf('兜底') >= 0)
        ? '\n（用的是通用结构识别，列名可能对不齐，导入后可在网站里改）' : '';
      if (confirm('识别方式：' + mode + '\n识别到 ' + first.rows.length + ' 条' + note +
                  '\n\n导出 CSV？\n（导出后在 InternHub「📚 备考方案」页底部上传，或直接粘贴导入）')) {
        download(first.rows);
      }
    } catch (e) {
      alert('采集出错：' + (e && e.message ? e.message : e));
    } finally {
      setStatus('📥 采集本页岗位');
      busy = false;
    }
  }

  // __BOOKMARK_CUT__ 书签版从这里截断（书签版不需要悬浮按钮）
  function mountButtons() {
    btn = document.createElement('button');
    btn.textContent = '📥 采集本页岗位';
    btn.style.cssText = 'position:fixed;right:18px;bottom:72px;z-index:999999;padding:10px 14px;' +
      'background:#0a6cb0;color:#fff;border:none;border-radius:8px;cursor:pointer;font-size:14px;' +
      'box-shadow:0 2px 8px rgba(0,0,0,.25)';
    btn.onclick = onClick;
    document.body.appendChild(btn);

    diagBtn = document.createElement('button');
    diagBtn.textContent = '🐞 结构诊断';
    diagBtn.title = '抓不到数据时点它：会导出一份页面结构说明，发给开发者就能定位';
    diagBtn.style.cssText = 'position:fixed;right:18px;bottom:118px;z-index:999999;padding:6px 10px;' +
      'background:#6e7781;color:#fff;border:none;border-radius:8px;cursor:pointer;font-size:12px;opacity:.85';
    diagBtn.onclick = function () { try { diagnose(); } catch (e) { alert('诊断失败：' + e.message); } };
    document.body.appendChild(diagBtn);
  }
  mountButtons();
  setInterval(function () {
    if (document.body && (!btn || !document.body.contains(btn))) {
      btn = null; diagBtn = null; mountButtons();
    }
  }, 2500);

  // 调试/自测入口（本地脚本，不影响功能）
  window.__IHUB_COLLECTOR__ = { readGrid: readGrid, rowsFromGrid: rowsFromGrid,
    mapHeaders: mapHeaders, csv: csv, rowsFromCards: rowsFromCards, collect: onClick,
    diagnose: diagnose, detectGridsHeuristic: detectGridsHeuristic, rowCells: rowCells };
})();
"""


def _atomic_write(path: str, content: str) -> None:
    """先写临时文件再替换：生成失败时绝不把已能用的旧文件清空。

    （踩过的坑：`open(path,'w')` 会先截断文件，之后生成报错就把书签文件写成了空文件。）
    """
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(tmp, path)


def save_userscript(path: str = None) -> str:
    path = path or os.path.join(config.PROJECT_ROOT, "采集助手.user.js")
    content = build_js()                      # 先完整生成，再落盘
    _atomic_write(path, content)
    return path


_BOOKMARK_HEAD = "javascript:"
_BOOKMARK_TAIL = "onClick();})()"


def _minify(js: str) -> str:
    """去掉整行注释与缩进，压成一行。

    两个坑：
    1. 行尾 `// 注释` 压成一行后会把后面的代码全吞掉 → 先把 `;`/`{` 之后的行尾注释改成块注释；
    2. JS 的"自动分号插入(ASI)"会失效——上一行以 `)`/`}`/标识符结尾、下一行以 `(`/`[`/`+`/`-`
       开头时，两行会被连成一次函数调用/下标访问，直接语法报错。这里检测并补分号。
    """
    lines = []
    for line in js.split("\n"):
        s = line.strip()
        if not s or s.startswith("//"):
            continue
        m = re.match(r"^(.*?[{;])\s*//\s*(.+)$", s)
        if m and "*/" not in m.group(2):
            s = m.group(1) + "  /* " + m.group(2).strip() + " */"
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
    content = build_bookmarklet()             # 先完整生成，再落盘
    _atomic_write(path, content + "\n")
    return path


if __name__ == "__main__":
    print(save_userscript())
    print(save_bookmarklet())

