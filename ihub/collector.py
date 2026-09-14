# -*- coding: utf-8 -*-
"""页面采集助手：在你**已登录**的浏览器里，把当前页面的岗位列表导出 CSV（再导入 InternHub）。

合规要点：完全由你手动点击触发；只读取当前页面已渲染的内容；
不登录、不提交、不绕过验证码、不调用平台私有接口。
"""
import os

from . import config


def build_js() -> str:
    return r"""// ==UserScript==
// @name         采集助手（InternHub·本地本人使用）
// @namespace    internhub.local
// @version      1.0
// @description  在国聘/24365/BOSS/智联/牛客等页面一键把岗位导出 CSV，再导入 InternHub
// @match        *://*/*
// @grant        none
// ==/UserScript==
(function () {
  'use strict';

  const JOB_WORDS = /招聘|校招|实习|岗位|工程师|专员|经理|助理|顾问|设计|运营|研发|测试|开发|销售|管培/;
  const SKIP = /登录|注册|首页|关于|帮助|更多|下一页|上一页|隐私|协议|岗位职责|任职要求/;

  function clean(s) { return (s || '').replace(/\s+/g, ' ').trim(); }

  function guessCity(t) {
    const cities = ['潍坊','济南','青岛','烟台','威海','昆明','大理','曲靖','玉溪','丽江',
      '北京','上海','深圳','广州','成都','杭州','南京','武汉','西安','重庆','天津','长沙'];
    for (const c of cities) if (t.includes(c)) return c;
    return '';
  }

  function collect() {
    const rows = [];
    const seen = new Set();
    // 优先找“岗位卡片/列表项”，退化为所有链接
    const blocks = document.querySelectorAll('li, .job, .job-item, .position, .list-item, tr, .card, article');
    const pushFromEl = (el) => {
      const a = el.querySelector && el.querySelector('a[href]');
      if (!a) return;
      const title = clean(a.getAttribute('title') || a.innerText || '');
      const href = a.href || '';
      if (!title || title.length < 6 || SKIP.test(title) || !JOB_WORDS.test(title)) return;
      if (!/^https?:/.test(href)) return;
      if (seen.has(href)) return;
      const text = clean(el.innerText || '').slice(0, 220);
      // 公司名：卡片里第一行与标题不同的文本
      let company = '';
      const lines = (el.innerText || '').split('\n').map(clean).filter(Boolean);
      for (const ln of lines) {
        if (ln !== title && ln.length >= 4 && ln.length <= 30 && !JOB_WORDS.test(ln).valueOf()) { company = ln; break; }
      }
      if (!company) {
        for (const ln of lines) { if (ln !== title && ln.length >= 4 && ln.length <= 30) { company = ln; break; } }
      }
      seen.add(href);
      rows.push({ title: title, company: company, city: guessCity(text) || guessCity(title), link: href, text: text });
    };
    if (blocks.length) blocks.forEach(pushFromEl);
    if (rows.length < 5) document.querySelectorAll('a[href]').forEach(pushFromEl);
    return rows;
  }

  function csv(rows) {
    const head = ['岗位', '公司', '城市', '学历', '标签', '链接', '截止日期', '描述', '岗位类型', '届别', '来源'];
    const host = location.hostname.replace(/^www\./, '');
    const lines = [head.join(',')];
    for (const r of rows) {
      const cells = [r.title, r.company, r.city, '', host, r.link, '', (r.text || '').replace(/"/g, '""'),
                     '秋招', '2027届', host];
      lines.push(cells.map(v => '"' + String(v).replace(/"/g, '""') + '"').join(','));
    }
    return '\ufeff' + lines.join('\r\n');
  }

  function download(rows) {
    const blob = new Blob([csv(rows)], { type: 'text/csv;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = '岗位采集_' + location.hostname + '_' + new Date().toISOString().slice(0, 10) + '.csv';
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 3000);
  }

  function onClick() {
    const rows = collect();
    if (!rows.length) { alert('没识别到岗位：请先在页面上显示出岗位列表（滚动加载完）再点一次。'); return; }
    if (confirm('识别到 ' + rows.length + ' 条岗位，导出 CSV？\n（导出后在 InternHub「📚 备考方案 → 导入 CSV」里一键入库）')) download(rows);
  }

  const btn = document.createElement('button');
  btn.textContent = '📥 采集本页岗位';
  btn.style.cssText = 'position:fixed;right:18px;bottom:72px;z-index:999999;padding:10px 14px;' +
    'background:#0a6cb0;color:#fff;border:none;border-radius:8px;cursor:pointer;font-size:14px;' +
    'box-shadow:0 2px 8px rgba(0,0,0,.25)';
  btn.onclick = onClick;
  window.addEventListener('load', () => document.body.appendChild(btn));
})();
"""


def save_userscript(path: str = None) -> str:
    path = path or os.path.join(config.PROJECT_ROOT, "采集助手.user.js")
    with open(path, "w", encoding="utf-8") as f:
        f.write(build_js())
    return path
