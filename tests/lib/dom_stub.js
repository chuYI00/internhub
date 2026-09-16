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
    this._value = undefined;
    this._uid = ++uid;
    this.href = '';
    this.style = { cssText: '' };
    this.checked = false;          // 浏览器里是真实属性
    this.readOnly = false;
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
  set innerText(v) { this._ownText = String(v); this.children = []; }
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

/* ---- 浏览器里这些是"反射属性"（读属性 == 读 attribute），脚本会直接用 ---- */
['id', 'name', 'type', 'placeholder', 'title', 'htmlFor', 'role'].forEach(prop => {
  const attrName = prop === 'htmlFor' ? 'for' : prop;
  Object.defineProperty(El.prototype, prop, {
    get() { const v = this.getAttribute(attrName); return v === null ? '' : v; },
    set(v) { this.setAttribute(attrName, v); },
    configurable: true,
  });
});

/* ---- 表单相关：给网申助手自测用 ---- */
Object.defineProperty(El.prototype, 'options', {
  get() {
    if (this.tagName !== 'SELECT') return undefined;
    return this.children.filter(c => c.tagName === 'OPTION');
  },
  configurable: true,
});
Object.defineProperty(El.prototype, 'selected', {
  get() { return !!this._selected; },
  set(v) {
    this._selected = !!v;
    if (v && this.parentElement && this.parentElement.tagName === 'SELECT') {
      (this.parentElement.options || []).forEach(o => { if (o !== this) o._selected = false; });
    }
  },
  configurable: true,
});
Object.defineProperty(El.prototype, 'selectedIndex', {
  get() {
    if (this.tagName !== 'SELECT') return -1;
    const opts = this.options || [];
    const i = opts.findIndex(o => o._selected);
    if (i >= 0) return i;
    return opts.length ? 0 : -1;
  },
  configurable: true,
});
function optionValue(el) {
  const v = el.getAttribute('value');
  return v === null ? el.textContent : v;
}
Object.defineProperty(El.prototype, 'value', {
  get() {
    if (this.tagName === 'SELECT') {
      const opts = this.options || [];
      const sel = opts.filter(o => o._selected)[0] || opts[0];
      return sel ? optionValue(sel) : '';
    }
    if (this.tagName === 'OPTION') return optionValue(this);
    return this._value === undefined ? '' : this._value;
  },
  set(v) {
    if (this.tagName === 'SELECT') {
      const opts = this.options || [];
      const target = opts.filter(o => optionValue(o) === String(v))[0];
      opts.forEach(o => { o._selected = false; });
      if (target) target._selected = true;
      this._value = String(v);
      return;
    }
    this._value = String(v);
  },
  configurable: true,
});
Object.defineProperty(El.prototype, 'isContentEditable', {
  get() { return this.getAttribute('contenteditable') === 'true'; },
  configurable: true,
});
Object.defineProperty(El.prototype, 'previousElementSibling', {
  get() {
    if (!this.parentElement) return null;
    const sibs = this.parentElement.children.filter(c => c.tagName !== '#TEXT');
    const i = sibs.indexOf(this);
    return i > 0 ? sibs[i - 1] : null;
  },
  configurable: true,
});
El.prototype.closest = function (sel) {
  let n = this;
  while (n && n.tagName !== '#TEXT') {
    if (matches(n, sel)) return n;
    n = n.parentElement;
  }
  return null;
};
El.prototype.getBoundingClientRect = function () {
  return { width: 120, height: 24, left: 0, top: 0, right: 120, bottom: 24 };
};
El.prototype.dispatchEvent = function (ev) {
  (this._events = this._events || []).push(ev && ev.type);
  const h = this._listeners && this._listeners[ev && ev.type];
  if (h) h.forEach(fn => fn(ev));
  return true;
};
El.prototype.addEventListener = function (type, fn) {
  this._listeners = this._listeners || {};
  (this._listeners[type] = this._listeners[type] || []).push(fn);
};
El.prototype.contains = function (node) {
  if (node === this) return true;
  return this.descendants.indexOf(node) >= 0;
};

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

/* ================= 表单构造（网申助手自测用） ================= */

/** <div class="row"><span>姓名</span><input placeholder="请输入姓名"></div> */
function fieldRow(labelText, inputEl, tag) {
  const row = new El(tag || 'div');
  row.setAttribute('class', 'form-row');
  if (labelText) { const sp = new El('span'); sp.appendText(labelText); row.appendChild(sp); }
  row.appendChild(inputEl);
  return row;
}

/** 新建 input/textarea */
function input(opts) {
  const o = opts || {};
  const e = new El(o.tag || 'input');
  if (o.type) e.setAttribute('type', o.type);
  if (o.name) e.setAttribute('name', o.name);
  if (o.id) e.setAttribute('id', o.id);
  if (o.placeholder) e.setAttribute('placeholder', o.placeholder);
  if (o.ariaLabel) e.setAttribute('aria-label', o.ariaLabel);
  if (o.value) e.value = o.value;
  if (o.nowrap === false) e._nowrap = false;
  return e;
}

/** 新建 <select>，opts 例：['', '男', '女'] 或 [{text:'本科及以上', value:'bk'}] */
function select(options, opts) {
  const e = new El('select');
  const o = opts || {};
  if (o.name) e.setAttribute('name', o.name);
  (options || []).forEach((op, i) => {
    const opt = new El('option');
    const text = typeof op === 'string' ? op : op.text;
    const value = typeof op === 'string' ? op : (op.value === undefined ? op.text : op.value);
    if (value !== '') opt.setAttribute('value', value);
    opt.appendText(text);
    if (i === 0) opt._selected = true;           // 浏览器默认选中第一个
    e.appendChild(opt);
  });
  if (o.selected) e.value = o.selected;
  return e;
}

/** 表格式老表单：<table><tr><td>姓名</td><td><input></td></tr>… */
function labelTable(pairs) {
  const t = new El('table');
  pairs.forEach(([labelText, ctrl]) => {
    const tr = new El('tr');
    const td1 = new El('td'); td1.appendText(labelText);
    const td2 = new El('td'); td2.appendChild(ctrl);
    tr.appendChild(td1); tr.appendChild(td2);
    t.appendChild(tr);
  });
  return t;
}

/** 单选组：<div><span>性别</span><label><input type=radio name=sex value=男>男</label>…</div> */
function radioGroup(labelText, name, values) {
  const box = new El('div');
  box.setAttribute('class', 'radio-group');
  if (labelText) { const sp = new El('span'); sp.appendText(labelText); box.appendChild(sp); }
  const inputs = [];
  values.forEach(v => {
    const lab = new El('label');
    const r = new El('input');
    r.setAttribute('type', 'radio');
    r.setAttribute('name', name);
    r.setAttribute('value', v);
    lab.appendChild(r);
    lab.appendText(v);
    box.appendChild(lab);
    inputs.push(r);
  });
  box._radios = inputs;
  return box;
}

/** 组装 vm 沙箱（网申助手/采集助手都能用） */
function buildSandbox(root, opts) {
  const o = opts || {};
  const store = new Map();
  const listeners = {};
  const sandbox = {
    console, setTimeout, clearTimeout, setInterval: () => 0, clearInterval: () => {},
    confirm: o.confirm || (() => true),
    alert: msg => { sandbox.__alert = msg; },
    location: { hostname: o.hostname || 'job.example.com', href: 'https://job.example.com/apply' },
    getComputedStyle: () => ({ overflowY: 'visible' }),
    Blob: class { constructor(parts) { this.parts = parts; } },
    URL: { createObjectURL: () => 'blob:x', revokeObjectURL: () => {} },
    Event: class { constructor(type, init) { this.type = type; Object.assign(this, init || {}); } },
    localStorage: {
      getItem: k => (store.has(k) ? store.get(k) : null),
      setItem: (k, v) => store.set(k, String(v)),
      removeItem: k => store.delete(k),
      clear: () => store.clear(),
    },
    HTMLInputElement: { prototype: {} },
    HTMLTextAreaElement: { prototype: {} },
    HTMLSelectElement: { prototype: {} },
    postMessage: () => {},
    addEventListener: (type, fn) => { (listeners[type] = listeners[type] || []).push(fn); },
  };
  // 让 setNative 能拿到 value 的原生 setter
  Object.defineProperty(sandbox.HTMLInputElement.prototype, 'value', {
    set(v) { this._value = String(v); }, get() { return this._value; }, configurable: true,
  });
  Object.defineProperty(sandbox.HTMLTextAreaElement.prototype, 'value', {
    set(v) { this._value = String(v); }, get() { return this._value; }, configurable: true,
  });
  Object.defineProperty(sandbox.HTMLSelectElement.prototype, 'value', {
    set(v) { this._value = String(v); }, get() { return this._value; }, configurable: true,
  });
  sandbox.window = sandbox;
  sandbox.document = makeDocument(root);
  sandbox.document.getElementById = id => root.descendants.filter(
    d => d.getAttribute('id') === id)[0] || null;
  sandbox.document.body = root;
  sandbox.top = sandbox;
  sandbox.parent = sandbox;
  sandbox.frames = [];
  sandbox.self = sandbox;
  sandbox.__listeners = listeners;
  return sandbox;
}

module.exports = {
  El, makeDocument, table, grid, cards, matchAll, matches,
  fieldRow, input, select, labelTable, radioGroup, buildSandbox,
};
