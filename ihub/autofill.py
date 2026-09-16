# -*- coding: utf-8 -*-
"""网申自动填写助手 v2：根据个人资料生成本地用户脚本（Tampermonkey）。

设计原则（合规、安全）：
- 只在**你本人打开的网页**上工作，由你点按钮触发填写，**不登录、不提交、不绕过验证码、不联网**；
- 资料来自本机 data/profile.json，可以在页面上就地补改（存在浏览器 localStorage，不出本机）；
- 填充后逐个高亮，由你核对后再自己点提交。

v2 相比 v1 的改进（v1 的致命问题：把整个表单的文字当成字段名，导致乱填）：
1. **标签识别更准**：aria-label / aria-labelledby / placeholder / title / data-* / name / id /
   <label for> / 包裹 label / 最近的"小容器"文字（容器里控件数 ≤2 才采用）/ 前一个兄弟文本 / 表格上一格
2. **支持控件类型**：text、textarea、select（含学历"本科→本科及以上"这类模糊匹配）、
   radio（性别等）、date/month（自动格式化）、number（GPA 去掉 /4.0）、tel、email、contenteditable 富文本
3. **字段更全**：政治面貌、民族、籍贯、学院、排名、紧急联系人、期望城市/薪资、到岗时间、项目经历等
4. **面板式交互**：右下角小按钮 → 展开资料面板，可当场补改缺失项、看到会填什么，再选择"只填空/覆盖"
5. **支持 iframe**：很多网申系统把表单放在 iframe 里，点一次会向所有子框架广播（postMessage）
6. **SPA 友好**：按钮被前端框架冲掉会自动重新挂上
"""
import json
import os

from . import config, profile as profile_mod

SCRIPT_NAME = "网申助手.user.js"

# 嵌入脚本的资料键（多出来的键也会一起带上，面板里能改）
KEYS = [
    "name", "gender", "birth", "political", "nation", "idcard",
    "phone", "email", "wechat", "qq",
    "school", "college", "major", "degree", "edu_range", "enroll", "graduate_year",
    "gpa", "rank", "city", "hometown", "address", "postal",
    "english", "certificates", "scholarship",
    "intent", "expected_city", "expected_salary", "available",
    "self_eval", "highlights", "skills", "experiences",
    "emergency_name", "emergency_phone", "emergency_relation",
]

_TEMPLATE = r"""// ==UserScript==
// @name         网申助手 v2（本地·本人使用）
// @namespace    internhub.local
// @version      2.1
// @description  在网申/校招表单页一键填入个人资料；本人点击触发，不代登录、不代提交、不联网
// @match        *://*/*
// @match        file:///*
// @grant        GM_getValue
// @grant        GM_setValue
// @grant        GM_deleteValue
// @run-at       document-idle
// ==/UserScript==
// 注意：这里故意声明 GM_* 权限而不是 @grant none。
// @grant none 时脚本会以"页面脚本"的方式注入，遇到政府/国企网站的严格内容安全策略(CSP)会被拦掉，
// 表现就是"页面上什么都没有"。声明 GM_* 后 Tampermonkey 在自己的沙箱里执行，不受页面 CSP 影响。
(function () {
  'use strict';

  var BASE = __PAYLOAD__;
  var LS_KEY = 'ihub_profile_overrides_v1';

  /* ==================== 存储（优先油猴存储，退化为 localStorage） ==================== */
  var GM_OK = (typeof GM_getValue === 'function' && typeof GM_setValue === 'function');
  function storeGet(k) {
    try { if (GM_OK) return GM_getValue(k, null); } catch (e) {}
    try { return localStorage.getItem(k); } catch (e) {}
    return null;
  }
  function storeSet(k, v) {
    try { if (GM_OK) { GM_setValue(k, v); return true; } } catch (e) {}
    try { localStorage.setItem(k, v); return true; } catch (e) {}
    return false;
  }
  function storeDel(k) {
    try { if (typeof GM_deleteValue === 'function') { GM_deleteValue(k); return true; } } catch (e) {}
    try { localStorage.removeItem(k); return true; } catch (e) {}
    return false;
  }

  /* ==================== 资料 ==================== */
  function overrides() {
    try { return JSON.parse(storeGet(LS_KEY) || '{}') || {}; } catch (e) { return {}; }
  }
  function readOverrides() { return overrides(); }
  function setOverride(k, v) {
    var o = overrides();
    if (v) { o[k] = v; } else { delete o[k]; }
    storeSet(LS_KEY, JSON.stringify(o));
  }
  function clearOverrides() { storeDel(LS_KEY); }
  function P() { return Object.assign({}, BASE, overrides()); }

  /* ==================== 字段字典 ==================== */
  // keys 里不要放"城市""时间"这种会跟别的字段打架的短词；匹配时取"命中关键词最长"的那个字段
  var FIELDS = [
    { k: 'name',      label: '姓名',     keys: ['姓名', '真实姓名', '中文姓名', 'name', 'fullname'] },
    { k: 'gender',    label: '性别',     keys: ['性别', 'gender', 'sex'] },
    { k: 'birth',     label: '出生日期', keys: ['出生日期', '出生年月', '生日', 'birthday', 'birth'] },
    { k: 'political', label: '政治面貌', keys: ['政治面貌', '政治面貌情况', 'party'] },
    { k: 'nation',    label: '民族',     keys: ['民族', 'nation', 'ethnic'] },
    { k: 'idcard',    label: '身份证号', keys: ['身份证号', '身份证件号', '身份证', 'idcard', 'idnumber'] },
    { k: 'phone',     label: '手机号',   keys: ['手机号', '手机号码', '联系电话', '联系方式', '手机', '电话', 'phone', 'mobile', 'tel'] },
    { k: 'email',     label: '邮箱',     keys: ['电子邮箱', '邮箱', '邮件', 'email', 'mail'] },
    { k: 'wechat',    label: '微信',     keys: ['微信号', '微信', 'wechat', 'weixin'] },
    { k: 'qq',        label: 'QQ',       keys: ['qq号', 'qq号码', 'qq'] },
    { k: 'school',    label: '毕业院校', keys: ['毕业院校', '毕业学校', '就读院校', '学校名称', '所在院校', '院校', '学校', 'school', 'university'] },
    { k: 'college',   label: '学院',     keys: ['学院', '院系', '系别', '所在学院', 'college', 'department', 'faculty'] },
    { k: 'major',     label: '专业',     keys: ['所学专业', '专业名称', '就读专业', '专业', 'major'] },
    { k: 'degree',    label: '学历',     keys: ['学历', '学位', '最高学历', 'degree', 'education'] },
    { k: 'edu_range', label: '就读时间', keys: ['在校时间', '就读时间', '起止时间', '就读起止', '教育起止'] },
    { k: 'enroll',    label: '入学时间', keys: ['入学时间', '入学年月', '入学年份', 'enrollment'] },
    { k: 'graduate_year', label: '毕业时间', keys: ['毕业时间', '毕业年月', '毕业年份', '预计毕业', 'graduation', 'graduate'] },
    { k: 'gpa',       label: 'GPA',      keys: ['gpa', '绩点', '平均分', '平均成绩'] },
    { k: 'rank',      label: '专业排名', keys: ['专业排名', '年级排名', '排名', 'rank'] },
    { k: 'city',      label: '现居地',   keys: ['现居住地', '现居地', '目前居住', '居住城市', '所在地', '当前城市', '现居', 'currentcity'] },
    { k: 'hometown',  label: '籍贯',     keys: ['籍贯', '生源地', '户籍所在地', '户籍地', '户口所在地', '民族籍贯', 'hometown', 'nativeplace'] },
    { k: 'address',   label: '通讯地址', keys: ['通讯地址', '联系地址', '邮寄地址', '详细地址', '家庭住址', 'address'] },
    { k: 'postal',    label: '邮编',     keys: ['邮编', '邮政编码', 'postal', 'zip'] },
    { k: 'english',   label: '外语水平', keys: ['外语水平', '英语水平', '英语等级', '四六级', 'cet', 'englishlevel'] },
    { k: 'certificates', label: '证书',  keys: ['证书', '资格证书', '职业资格', '资格证', 'certificate'] },
    { k: 'scholarship', label: '奖学金/荣誉', keys: ['奖学金', '获奖情况', '荣誉', '奖励', 'scholarship', 'award', 'honor'] },
    { k: 'intent',    label: '求职意向', keys: ['求职意向', '应聘岗位', '意向岗位', '期望职位', '申请职位', '目标岗位', '求职方向'] },
    { k: 'expected_city', label: '期望城市', keys: ['期望工作城市', '期望城市', '意向城市', '期望工作地', '工作城市', 'preferredcity'] },
    { k: 'expected_salary', label: '期望薪资', keys: ['期望薪资', '期望月薪', '薪资要求', '期望年薪'] },
    { k: 'available', label: '到岗时间', keys: ['到岗时间', '最快到岗', '可实习时间', '实习时长', '可到岗'] },
    { k: 'self_eval', label: '自我评价', keys: ['自我评价', '自我介绍', '个人评价', '个人简介', '个人优势', 'selfevaluation', 'aboutme'] },
    { k: 'experiences', label: '项目/实习经历', keys: ['项目经历', '实习经历', '工作经历', '实践经历', '项目经验', 'experience'] },
    { k: 'skills',    label: '技能特长', keys: ['技能', '专业技能', '特长', '擅长', 'skill'] },
    { k: 'highlights', label: '个人亮点', keys: ['个人亮点', '主要成绩', '优势亮点', 'highlight'] },
    { k: 'emergency_name', label: '紧急联系人', keys: ['紧急联系人', '紧急联络人', '联系人姓名', 'emergencyname'] },
    { k: 'emergency_phone', label: '紧急联系人电话', keys: ['紧急联系人电话', '紧急联系电话', '联系人电话', 'emergencyphone'] },
    { k: 'emergency_relation', label: '与本人关系', keys: ['与本人关系', '联系人与本人关系', '关系', 'relation'] },
    { k: 'marital',   label: '婚姻状况', keys: ['婚姻状况', '婚否', 'marital'] },
  ];

  /* ==================== 工具 ==================== */
  function norm(s) { return String(s == null ? '' : s).replace(/[\s\u3000*＊:：?？()（）、,，.。/|]/g, '').toLowerCase(); }
  function visText(el) { return String((el && (el.innerText || el.textContent)) || '').replace(/\s+/g, ' ').trim(); }
  function isVisible(el) {
    if (!el || !el.getBoundingClientRect) return true;
    try {
      var r = el.getBoundingClientRect();
            if (r && r.width === 0 && r.height === 0) return false;  /* 隐藏域/折叠区 */
    } catch (e) {}
    return true;
  }
  function controlCount(node) {
    if (!node || !node.querySelectorAll) return 0;
    try { return node.querySelectorAll('input,textarea,select,[contenteditable="true"]').length; } catch (e) { return 0; }
  }
  function attr(el, n) { try { return el.getAttribute ? el.getAttribute(n) : null; } catch (e) { return null; } }

  /* ==================== 标签识别（v1 的坑就在这） ==================== */
  function labelOf(el, doc) {
    var parts = [];
    function push(v) { if (v) parts.push(String(v)); }

    push(attr(el, 'aria-label'));
    var lb = attr(el, 'aria-labelledby');
    if (lb && doc.getElementById) {
      lb.split(/\s+/).forEach(function (id) {
        var n = doc.getElementById(id);
        if (n) push(visText(n));
      });
    }
    push(attr(el, 'placeholder'));
    push(attr(el, 'title'));
    push(attr(el, 'data-label'));
    push(attr(el, 'data-field'));
    push(attr(el, 'data-name'));
    push(attr(el, 'name'));

    if (el.id && doc.querySelector) {
      var forLab = null;
      try { forLab = doc.querySelector('label[for="' + String(el.id).replace(/"/g, '\\"') + '"]'); } catch (e) {}
      if (forLab) push(visText(forLab));
    }
    var wrapLab = el.closest ? el.closest('label') : null;
    if (wrapLab) push(visText(wrapLab));

    // 逐级向上：只采信"控件数 ≤2 的小容器"里的文字（避免把整个表单当字段名）
    var n = el.parentElement, depth = 0;
    while (n && depth < 4) {
      if (controlCount(n) <= 2) {
        var t = visText(n);
        if (t && t.length <= 40) { push(t); break; }
        if (t) break;
      }
      n = n.parentElement; depth++;
    }

    // 前面的兄弟文本：<span>姓名</span><input>
    var sib = el.previousElementSibling, hop = 0;
    while (sib && hop < 3) {
      if (controlCount(sib) === 0) {
        var st = visText(sib);
        if (st && st.length <= 20) push(st);
        break;
      }
      sib = sib.previousElementSibling; hop++;
    }

    // 老式表格：<td>姓名</td><td><input></td>
    var td = el.closest ? el.closest('td') : null;
    if (td && td.previousElementSibling) push(visText(td.previousElementSibling));

    return parts.filter(Boolean).join(' | ');
  }

  // 返回命中的字段（取"命中关键词最长"者，降低误配）
  function bestField(label) {
    var L = norm(label);
    if (!L) return null;
    var best = null, bestLen = 0;
    for (var i = 0; i < FIELDS.length; i++) {
      var f = FIELDS[i];
      for (var j = 0; j < f.keys.length; j++) {
        var nk = norm(f.keys[j]);
        if (!nk || nk.length < 2) continue;
        if (L.indexOf(nk) >= 0 && nk.length > bestLen) { best = f; bestLen = nk.length; }
      }
    }
    return best;
  }

  /* ==================== 写值 ==================== */
  function fire(el) {
    ['input', 'change', 'blur'].forEach(function (t) {
      try { el.dispatchEvent(new Event(t, { bubbles: true })); } catch (e) {}
    });
  }
  function setNative(el, val) {
    var tag = el.tagName, proto = null;
    if (tag === 'TEXTAREA') proto = window.HTMLTextAreaElement && HTMLTextAreaElement.prototype;
    else if (tag === 'SELECT') proto = window.HTMLSelectElement && HTMLSelectElement.prototype;
    else proto = window.HTMLInputElement && HTMLInputElement.prototype;
    var d = proto && Object.getOwnPropertyDescriptor(proto, 'value');
    if (d && d.set) d.set.call(el, val); else el.value = val;
    fire(el);
  }
  function mark(el, ok) {
    try { el.style.outline = ok ? '2px solid #1a7f37' : '2px solid #d97706'; el.style.outlineOffset = '1px'; } catch (e) {}
  }
  function looseMatch(want, text) {
    var w = norm(want), t = norm(text);
    if (!w || !t) return false;
    if (w === t) return true;
    if (w.indexOf(t) >= 0 || t.indexOf(w) >= 0) return true;
        if (w.length >= 2 && t.length >= 2 && w.slice(0, 2) === t.slice(0, 2)) return true;  /* 云南大理 ↔ 云南省 */
    return false;
  }
  function fillSelect(el, val) {
    var opts = Array.prototype.slice.call(el.options || []);
    if (!opts.length) return false;
    var hit = null, i;
        for (i = 0; i < opts.length; i++) {  /* 1) 精确 */
      if (norm(opts[i].value) === norm(val) || norm(opts[i].textContent) === norm(val)) { hit = opts[i]; break; }
    }
        if (!hit) for (i = 0; i < opts.length; i++) {  /* 2) 互相包含/前两字相同 */
      if (looseMatch(val, opts[i].textContent) || looseMatch(val, opts[i].value)) { hit = opts[i]; break; }
    }
    if (!hit) return false;
    try { el.value = hit.value; } catch (e) {}
    if (el.value !== hit.value) { hit.selected = true; }
    if (el.selectedIndex >= 0 && el.options[el.selectedIndex] && norm(el.options[el.selectedIndex].textContent) !== norm(hit.textContent)) {
            hit.selected = true;  /* 有些框架要手动置 selected */
    }
    fire(el);
    return true;
  }
  function toYM(val, withDay) {
    var s = String(val || '');
    var ym = s.match(/(19|20)\d{2}[.\-\/年]?\s*(\d{1,2})?/);
    var y = (s.match(/(19|20)\d{2}/) || [])[0] || '';
    if (!y) return '';
    var mo = ym && ym[2] ? String(ym[2]).padStart(2, '0') : '';
    if (withDay && mo) return y + '-' + mo + '-01';
    if (withDay) return y + '-01-01';
    return mo ? y + '-' + mo : y + '-01';
  }
  function adapt(el, raw) {
    var t = String(attr(el, 'type') || 'text').toLowerCase(), s = String(raw == null ? '' : raw);
    if (el.tagName === 'SELECT') return s;
    if (t === 'date') return toYM(s, true);
    if (t === 'month') return toYM(s, false);
    if (t === 'number' || t === 'range') { var m = s.match(/-?\d+(\.\d+)?/); return m ? m[0] : ''; }
    if (t === 'tel') return s.replace(/[^\d+\-]/g, '');
    if (t === 'email') { var e = s.match(/[\w.+-]+@[\w-]+\.[\w.]+/); return e ? e[0] : s; }
    return s;
  }

  /* ==================== 主流程 ==================== */
  function hasValue(el) {
    if (el.isContentEditable) return visText(el).length > 0;
    if (el.tagName === 'SELECT') return el.selectedIndex > 0;
    return String(el.value == null ? '' : el.value).trim().length > 0;
  }
  function collect(doc) {
    var out = [];
    var list;
    try { list = doc.querySelectorAll('input,textarea,select,[contenteditable="true"]'); } catch (e) { return out; }
    Array.prototype.slice.call(list).forEach(function (el) {
      var t = String(attr(el, 'type') || 'text').toLowerCase();
      if (['hidden', 'file', 'submit', 'button', 'reset', 'image', 'password'].indexOf(t) >= 0) return;
      if (!isVisible(el)) return;
      out.push(el);
    });
    return out;
  }

  function fillRadios(doc, prof, onlyEmpty, report) {
    var groups = {};
    var radios;
    try { radios = doc.querySelectorAll('input[type=radio]'); } catch (e) { return 0; }
    Array.prototype.slice.call(radios).forEach(function (r) {
      if (!isVisible(r)) return;
      var key = r.name || ('__g' + Array.prototype.indexOf.call(radios, r));
      (groups[key] = groups[key] || []).push(r);
    });
    var n = 0;
    Object.keys(groups).forEach(function (key) {
      var g = groups[key];
      if (onlyEmpty && g.some(function (r) { return r.checked; })) return;
      var f = bestField(labelOf(g[0], doc) + ' ' + (g[0].name || ''));
      if (!f) return;
      var val = prof[f.k];
      if (!val) return;
      var hit = g.filter(function (r) {
        var own = visText(r.closest && r.closest('label') ? r.closest('label') : r.parentElement);
        return norm(own) === norm(val) || looseMatch(val, own) || norm(r.value) === norm(val);
      })[0];
      if (!hit) return;
      try { hit.checked = true; fire(hit); mark(hit, true); n++; if (report) report.push(f.label + '→' + val); } catch (e) {}
    });
    return n;
  }

  function fillDoc(doc, mode) {
    var prof = P();
    var onlyEmpty = mode !== 'overwrite';
    var report = [];
    var filled = fillRadios(doc, prof, onlyEmpty, report);
    collect(doc).forEach(function (el) {
      var t = String(attr(el, 'type') || 'text').toLowerCase();
      if (t === 'radio' || t === 'checkbox') return;
      if (onlyEmpty && hasValue(el)) return;
      var f = bestField(labelOf(el, doc));
      if (!f) return;
      var raw = prof[f.k];
      if (!raw) return;
      var val = adapt(el, raw);
      if (!val) return;
      var ok = false;
      try {
        if (el.tagName === 'SELECT') ok = fillSelect(el, val);
        else if (el.isContentEditable) { el.innerText = val; fire(el); ok = true; }
        else if (String(attr(el, 'readonly')) === 'true' || el.readOnly) { return; }
        else { setNative(el, val); ok = true; }
      } catch (e) { ok = false; }
      if (ok) { mark(el, true); filled++; report.push(f.label + '→' + String(val).slice(0, 14)); }
    });
    return { filled: filled, report: report };
  }

  /* ==================== 跨 iframe ==================== */
  // __BOOKMARK_CUT__ 书签版从这里截断（书签版没法往子框架注入脚本）
  var isTop = (function () { try { return window.top === window; } catch (e) { return false; } })();
  function broadcast(mode) {
    var msg = { __ihub: 'fill', mode: mode };
    try { for (var i = 0; i < window.frames.length; i++) window.frames[i].postMessage(msg, '*'); } catch (e) {}
  }
  window.addEventListener('message', function (ev) {
    var d = ev.data;
    if (!d || d.__ihub !== 'fill') return;
        if (ev.source === window) return;  /* 别理自己 */
    var st = fillDoc(document, d.mode);
    try {
      var up = isTop ? window : window.parent;
      up.postMessage({ __ihub: 'filled', n: st.filled }, '*');
    } catch (e) {}
  });

  /* ==================== 面板 ==================== */
  var panel = null, statusEl = null, listEl = null;

  function el(tag, css, text) {
    var d = document.createElement(tag);
    if (css) d.style.cssText = css;
    if (text != null) d.textContent = text;
    return d;
  }
  function btn(text, css, fn) {
    var b = el('button', 'padding:5px 9px;border:1px solid #d0d7de;border-radius:6px;background:#f6f8fa;' +
      'cursor:pointer;font-size:12px;' + (css || ''), text);
    b.type = 'button';
    b.addEventListener('click', fn);
    return b;
  }

  function refreshList() {
    if (!listEl) return;
    listEl.textContent = '';
    var prof = P(), ov = readOverrides();
    FIELDS.forEach(function (f) {
      var row = el('div', 'display:flex;gap:6px;align-items:center;margin:3px 0');
      var tag = el('div', 'flex:0 0 84px;color:' + (f.k in ov ? '#9a3412' : '#57606a') + ';font-size:12px', f.label + (f.k in ov ? ' *' : ''));
      var inp = el('input', 'flex:1;min-width:0;padding:3px 6px;border:1px solid #d0d7de;border-radius:5px;font-size:12px');
      inp.value = prof[f.k] || '';
      inp.placeholder = '未填（可在这里补）';
      inp.addEventListener('change', function () {
        var v = inp.value.trim();
        if (v === (BASE[f.k] || '')) setOverride(f.k, ''); else setOverride(f.k, v);
        refreshList();
      });
      row.appendChild(tag); row.appendChild(inp);
      listEl.appendChild(row);
    });
  }

  function doFill(mode) {
    var st = fillDoc(document, mode);
    broadcast(mode);
    if (statusEl) {
      statusEl.textContent = '已填 ' + st.filled + ' 个字段' +
        (st.filled ? '：' + st.report.slice(0, 6).join('，') + (st.report.length > 6 ? ' …' : '') : '（没有匹配到可填字段）');
    }
    setTimeout(function () {
      if (statusEl && st.filled === 0) {
        statusEl.textContent += '。若页面在 iframe 里，稍等 1 秒；也可以试试先点一下表单区域再点填入。';
      }
    }, 1200);
  }

  function buildPanel() {
    panel = el('div', 'position:fixed;right:16px;bottom:16px;z-index:2147483647;width:344px;max-height:74vh;' +
      'overflow:auto;background:#fff;border:1px solid #d0d7de;border-radius:10px;' +
      'box-shadow:0 8px 28px rgba(0,0,0,.2);font:13px/1.55 -apple-system,"Microsoft YaHei",sans-serif;color:#1f2328');
    var head = el('div', 'display:flex;align-items:center;justify-content:space-between;padding:8px 10px;' +
      'border-bottom:1px solid #eaeef2;background:#f6f8fa;border-radius:10px 10px 0 0');
    head.appendChild(el('b', 'font-size:13px', '📝 网申助手 v2'));
    var x = btn('收起', '', function () { panel.style.display = 'none'; if (fab) fab.style.display = 'block'; });
    head.appendChild(x);
    panel.appendChild(head);

    var body = el('div', 'padding:9px 10px');
    var bar = el('div', 'display:flex;gap:6px;flex-wrap:wrap;margin-bottom:6px');
    bar.appendChild(btn('填入空字段', 'background:#1f6feb;color:#fff;border-color:#1f6feb', function () { doFill('empty'); }));
    bar.appendChild(btn('覆盖全部', '', function () { doFill('overwrite'); }));
    bar.appendChild(btn('💾 记住修改', '', function () {
      if (statusEl) statusEl.textContent = '已记住（存在本机浏览器里，换网站也生效）';
    }));
    bar.appendChild(btn('恢复内置', '', function () { clearOverrides(); refreshList(); if (statusEl) statusEl.textContent = '已恢复 data/profile.json 里的资料'; }));
    body.appendChild(bar);

    statusEl = el('div', 'color:#57606a;font-size:12px;margin-bottom:6px', '资料改完直接点「填入空字段」。带 * 的是你在这里改过的值。');
    body.appendChild(statusEl);

    listEl = el('div');
    body.appendChild(listEl);
    body.appendChild(el('div', 'color:#8c959f;font-size:11px;margin-top:6px',
      '只在你本人点击时填表，不联网、不提交、不绕过验证码。定稿前请逐个核对。'));
    panel.appendChild(body);
    document.body.appendChild(panel);
    refreshList();
  }

  var fab = null;
  function buildFab() {
    fab = el('div', 'position:fixed;right:16px;bottom:16px;z-index:2147483647;padding:9px 12px;background:#1f6feb;' +
      'color:#fff;border-radius:22px;cursor:pointer;font:13px -apple-system,"Microsoft YaHei",sans-serif;' +
      'box-shadow:0 4px 14px rgba(0,0,0,.25);user-select:none', '📝 网申助手');
    fab.addEventListener('click', function () {
      if (!panel) buildPanel();
      panel.style.display = 'block';
      fab.style.display = 'none';
      refreshList();
    });
    document.body.appendChild(fab);
  }

  function ensureMounted() {
    if (document.body && (!fab || !document.body.contains(fab))) buildFab();
  }

  if (isTop) {
    ensureMounted();
        setInterval(ensureMounted, 2500);  /* SPA/前端框架会重渲染 body */
  }

  // 调试/自测入口（沙箱模式下写 window 可能被拒，忽略即可）
  try {
    window.__IHUB_AUTOFILL__ = {
      labelOf: labelOf, bestField: bestField, fillDoc: fillDoc, adapt: adapt,
      fillSelect: fillSelect, FIELDS: FIELDS, profile: P, setOverride: setOverride,
      getOverrides: readOverrides, clearOverrides: clearOverrides, buildPanel: buildPanel,
    };
  } catch (e) {}
})();
"""


def build_js(prof=None) -> str:
    prof = prof or profile_mod.load()
    data = {}
    for k in KEYS:
        v = prof.get(k, "")
        data[k] = v if v not in (None, "") else ""
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    return _TEMPLATE.replace("__PAYLOAD__", payload)


def save_userscript(path: str = None, prof=None) -> str:
    path = path or os.path.join(config.PROJECT_ROOT, SCRIPT_NAME)
    with open(path, "w", encoding="utf-8") as f:
        f.write(build_js(prof))
    return path


BOOKMARK_NAME = "网申书签.txt"
_BOOKMARK_HEAD = "javascript:"
_BOOKMARK_TAIL = "go();})()"


def _minify(js: str) -> str:
    """压成一行（去掉整行注释/缩进，并在 ASI 会出问题处补分号）。"""
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


def build_bookmarklet(prof=None) -> str:
    """从同一份源码生成书签版（免装扩展）：点书签即按「只填空字段」填一遍当前页。"""
    js = build_js(prof)
    idx = js.find("(function () {")
    body = js[idx:]
    sentinel = "// __BOOKMARK_CUT__"
    cut = body.find(sentinel)
    if cut < 0:
        raise RuntimeError("网申脚本缺少 __BOOKMARK_CUT__ 哨兵，无法生成书签版")
    body = body[:cut]
    body = _minify(body)
    for i in range(len(body) - 1):
        if body[i:i + 2] == "//" and (i == 0 or body[i - 1] != ":"):
            raise RuntimeError(
                f"书签版源码里有会吞代码的 // 注释（位置 {i}）：{body[max(0, i - 60):i + 60]!r}")
    boot = (
        "function go(){try{var st=fillDoc(document,'empty');var m='网申助手（书签版）：已填 '+st.filled+' 个字段';"
        "if(st.filled){m+='\\n'+st.report.slice(0,10).join('，');}"
        "else{m+='\\n\\n没匹配到字段。若是 iframe 表单，书签版填不了，请用油猴版；"
        "也可以先在页面滚动一下再点一次。';}"
        "m+='\\n\\n请逐个核对后再提交。';alert(m);}catch(e){alert('网申助手出错：'+e.message);}}"
    )
    return _BOOKMARK_HEAD + body + boot + _BOOKMARK_TAIL


def save_bookmarklet(path: str = None, prof=None) -> str:
    path = path or os.path.join(config.PROJECT_ROOT, BOOKMARK_NAME)
    with open(path, "w", encoding="utf-8") as f:
        f.write(build_bookmarklet(prof) + "\n")
    return path


if __name__ == "__main__":
    print(save_userscript())
    print(save_bookmarklet())
