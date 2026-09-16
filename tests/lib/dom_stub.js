/**
 * 极简 DOM 打桩（够采集助手用：limited 选择器 + 表格/网格/卡片构造）。
 * 不追求浏览器兼容，只求把采集逻辑跑起来做回归。
 */
'use strict';
let uid = 0;

class El {
  constructor(tag) {
    this.tagName = String(tag).toUpperCase();
    this.children = [];
    this.parentElement = null;
    this._attrs = {};
    this._text = '';
    this._cls = new Set();
    this._ownText = undefined;
    this.href = '';
    this.style = { cssText: '' };
    this._id = ++uid;
  }
  setAttribute(k, v) {
    this._attrs[k] = String(v);
    if (k === 'href') this.href = String(v);
    if (k === 'class') String(v).split(/\s+/).forEach(c => c && this._cls.add(c));
  }
  getAttribute(k) { return k in this._attrs ? this._attrs[k] : null; }
  get classList() { return { contains: c => this._cls.has(c) }; }
  appendChild(c) { c.parentElement = this; this.children.push(c); return c; }
  appendText(t) { const e = new El('#text'); e._text = t; e.parentElement = this; this.children.push(e); return e; }
  click() { this._clicked = true; if (typeof this.onclick === 'function') this.onclick(); }
  get textContent() {
    if (this._ownText !== undefined) return this._ownText;
    if (this.tagName === '#TEXT') return this._text;
    return this.children.map(c => c.textContent).join('');
  }
  set textContent(v) { this._ownText = String(v); this.children = []; }
  get innerText() {
    if (this._ownText !== undefined) return this._ownText;
    if (this.tagName === '#TEXT') return this._text;
    const BLOCK = /^(DIV|P|LI|TR|TABLE|SECTION|ARTICLE|H[1-6]|BR)$/;
    let out = '';
    for (const c of this.children) {
      const t = c.innerText;
      if (!t) continue;
      out += (BLOCK.test(c.tagName) && out) ? '\n' + t : t;
    }
    return out;
  }
  get descendants() {
    const out = [];
    const walk = n => n.children.forEach(c => { out.push(c); walk(c); });
    walk(this);
    return out;
  }
  querySelectorAll(sel) { return matchAll(this.descendants, sel); }
  querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
  get rows() { return this.descendants.filter(d => d.tagName === 'TR'); }
}

Object.defineProperty(El.prototype, 'cells', {
  get() {
    if (this.tagName !== 'TR') return undefined;
    return this.children.filter(c => c.tagName === 'TD' || c.tagName === 'TH');
  },
  configurable: true,
});

const SEL_RE = /^([a-zA-Z*]*)((?:[.#][\w-]+|\[[^\]]+\])*)$/;
const PART_RE = /[.#][\w-]+|\[[^\]]+\]/g;

function matches(el, sel) {
  const m = SEL_RE.exec(sel.trim());
  if (!m) return false;
  const tag = m[1];
  if (tag && tag !== '*' && el.tagName !== tag.toUpperCase()) return false;
  const parts = (m[2] || '').match(PART_RE) || [];
  for (const p of parts) {
    if (p[0] === '.') {
      if (!el._cls.has(p.slice(1))) return false;
    } else if (p[0] === '#') {
      if (el.getAttribute('id') !== p.slice(1)) return false;
    } else {
      const inner = p.slice(1, -1);
      const eq = inner.match(/^([\w-]+)(?:([*^$]?=)"?([^"]*)"?)?$/);
      if (!eq) return false;
      const name = eq[1], op = eq[2], val = eq[3];
      const actual = el.getAttribute(name);
      if (actual === null) return false;
      if (op === undefined) continue;
      if (op === '=' && actual !== val) return false;
      if (op === '*=' && !actual.includes(val)) return false;
      if (op === '^=' && !actual.startsWith(val)) return false;
      if (op === '$=' && !actual.endsWith(val)) return false;
    }
  }
  return true;
}

function matchAll(pool, sel) {
  const sels = String(sel).split(',').map(s => s.trim()).filter(Boolean);
  const out = [];
  for (const el of pool) {
    for (const s of sels) {
      if (matches(el, s)) { out.push(el); break; }
    }
  }
  return out;
}

function makeDocument(root) {
  return {
    body: root,
    querySelectorAll: sel => matchAll(root.descendants, sel),
    querySelector: sel => matchAll(root.descendants, sel)[0] || null,
    createElement: tag => new El(tag),
  };
}

function table(headers, rows) {
  const t = new El('table');
  const hr = new El('tr');
  headers.forEach(h => { const th = new El('th'); th.appendText(h); hr.appendChild(th); });
  t.appendChild(hr);
  rows.forEach(r => {
    const tr = new El('tr');
    r.forEach(v => {
      const td = new El('td');
      if (v && typeof v === 'object' && v.text !== undefined) {
        if (v.url) { const a = new El('a'); a.setAttribute('href', v.url); a.appendText(v.text); td.appendChild(a); }
        else td.appendText(v.text);
      } else td.appendText(String(v));
      tr.appendChild(td);
    });
    t.appendChild(tr);
  });
  return t;
}

function grid(headers, rows) {
  const g = new El('div');
  g.setAttribute('role', 'grid');
  const hr = new El('div');
  hr.setAttribute('role', 'row');
  headers.forEach(h => { const c = new El('div'); c.setAttribute('role', 'columnheader'); c.appendText(h); hr.appendChild(c); });
  g.appendChild(hr);
  rows.forEach(r => {
    const rr = new El('div');
    rr.setAttribute('role', 'row');
    r.forEach(v => { const c = new El('div'); c.setAttribute('role', 'gridcell'); c.appendText(String(v)); rr.appendChild(c); });
    g.appendChild(rr);
  });
  return g;
}

function cards(list) {
  const ul = new El('ul');
  list.forEach(([title, company, url, extra]) => {
    const li = new El('li');
    const a = new El('a'); a.setAttribute('href', url); a.appendText(title);
    li.appendChild(a);
    li.appendText('\n' + company + '\n' + (extra || ''));
    ul.appendChild(li);
  });
  return ul;
}

module.exports = { El, makeDocument, table, grid, cards, matchAll };
