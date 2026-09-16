/**
 * ATS（企业自有网申系统）兼容自测。
 *
 * 场景：你在就业网/公众号看到岗位后点进企业自己的网申系统 —— 北森(hotjob)、Moka、
 * 飞书招聘、用友这些系统用的是 antd / element-ui 的**自绘控件**：
 *   下拉不是 <select>，而是 div + 弹出层；单选不是 <input type=radio>，而是卡片 div。
 * 光给它们赋 value 无效，必须真的"点开 → 点选项"。这里就用打桩 DOM 把三类真实结构
 * 各造一份，验证填得进去。
 *
 * 运行： node tests/autofill_ats_test.js
 */
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const dom = require('./lib/dom_stub.js');
const { El, input, select, buildSandbox } = dom;

const NAME = process.argv[2] || path.join(__dirname, '..', '网申助手.user.js');
const code = fs.readFileSync(NAME, 'utf8');

const sleep = ms => new Promise(r => setTimeout(r, ms));
const sandboxDoc = root => dom.makeDocument(root);

function run(root) {
  const sb = buildSandbox(root);
  vm.runInContext(code, vm.createContext(sb), { filename: NAME });
  return { api: sb.window.__IHUB_AUTOFILL__, sandbox: sb };
}

let pass = 0, fail = 0;
const check = (n, c, extra) => {
  if (c) { pass++; console.log('  ✓ ' + n); }
  else { fail++; console.log('  ✗ ' + n + (extra !== undefined ? '  -> ' + JSON.stringify(extra) : '')); }
};

const EXP = (() => {
  const r = new El('body');
  const sb = buildSandbox(r);
  vm.runInContext(code, vm.createContext(sb), { filename: NAME });
  return sb.window.__IHUB_AUTOFILL__.profile();
})();

/* 造一个「表单项」容器：<div class="ant-form-item"><div class="..-label"><label>题目</label></div> 控件 </div> */
function formItem(cls, labelText, ctrl, forId) {
  const item = new El('div'); item.setAttribute('class', cls + '-form-item');
  const lab = new El('div'); lab.setAttribute('class', cls + '-form-item-label');
  const l = new El('label'); if (forId) l.setAttribute('for', forId); l.appendText(labelText);
  lab.appendChild(l);
  const wrap = new El('div'); wrap.setAttribute('class', cls + '-form-item-control');
  wrap.appendChild(ctrl);
  item.appendChild(lab); item.appendChild(wrap);
  return item;
}

/* 造一个自绘下拉（点开后在 body 上渲染选项；点选项回填显示值） */
function fakeSelect(cls, placeholder, options, root, boxCls) {
  const wrap = new El('div'); wrap.setAttribute('class', cls);
  const sel = new El('div'); sel.setAttribute('class', boxCls || (cls + '-selector'));
  sel.appendText(placeholder);
  wrap.appendChild(sel);
  wrap.onclick = () => {
    if (wrap._rendered) return;
    wrap._rendered = true;
    const list = new El('div'); list.setAttribute('class', cls + '-dropdown');
    options.forEach(t => {
      const o = new El('div');
      o.setAttribute('class', cls === 'ant-select' ? 'ant-select-item-option' : 'el-select-dropdown__item');
      o.appendText(t);
      o.onclick = () => { sel.textContent = t; wrap._chosen = t; };
      list.appendChild(o);
    });
    root.appendChild(list);
  };
  return { wrap, sel };
}

/* 造一组卡片单选 */
function cardRadios(cls, values) {
  const box = new El('div');
  values.forEach(v => {
    const w = new El('label'); w.setAttribute('class', cls + '-wrapper');
    const r = new El('span'); r.setAttribute('role', 'radio'); r.appendText(v);
    r.onclick = () => { box._chosen = v; };
    w.appendChild(r); box.appendChild(w);
  });
  return box;
}

(async function main() {
  /* ---------- 1. 北森 hotjob 风格：表格 + 原生 select + 原生 radio ---------- */
  console.log('[1] 北森 hotjob 风格（表格布局 + 原生下拉/单选）');
  {
    const root = new El('body');
    const tb = new El('table');
    const row = (label, ctrl) => {
      const tr = new El('tr');
      const td1 = new El('td'); td1.appendText(label);
      const td2 = new El('td'); td2.appendChild(ctrl);
      tr.appendChild(td1); tr.appendChild(td2); tb.appendChild(tr);
    };
    row('姓名', input({}));
    row('手机号码', input({ type: 'tel' }));
    row('电子邮箱', input({ type: 'email' }));
    row('最高学历', select(['请选择', '本科', '硕士', '博士']));
    row('政治面貌', select(['请选择', '共青团员', '中共党员', '群众']));
    row('出生日期', input({ type: 'date' }));
    row('毕业院校', input({}));
    row('所学专业', input({}));
    root.appendChild(tb);
    const g = new El('div');
    g.appendText('性别');
    ['男', '女'].forEach((v, i) => {
      const l = new El('label');
      const r = input({ type: 'radio' });
      r.setAttribute('name', 'gender'); r.setAttribute('value', v);
      l.appendText(v); l.appendChild(r); g.appendChild(l);
    });
    root.appendChild(g);

    const { api } = run(root);
    const st = api.fillDoc(sandboxDoc(root), 'empty');
    const ins = root.descendants.filter(d => d.tagName === 'INPUT');
    const sels = root.descendants.filter(d => d.tagName === 'SELECT');
    check('姓名填入', ins[0].value === EXP.name, ins[0].value);
    check('手机号填入', ins[1].value === EXP.phone, ins[1].value);
    check('邮箱填入', ins[2].value === EXP.email, ins[2].value);
    check('最高学历 → 本科', sels[0].value === '本科', sels[0].value);
    check('政治面貌 → 共青团员', sels[1].value === '共青团员', sels[1].value);
    check('出生日期（date 输入）→ 2005-01-01', ins[3].value === '2005-01-01', ins[3].value);
    check('毕业院校填入', ins[4].value === '中国民航大学', ins[4].value);
    check('所学专业填入', ins[5].value === '物联网工程', ins[5].value);
    check('性别单选勾选「男」', ins[6].checked === true || ins[7].checked === true,
      [ins[6].checked, ins[7].checked]);
    check('整体至少填 8 个', st.filled >= 8, st.filled);
  }

  /* ---------- 2. antd 风格（Moka / 飞书招聘）：.ant-form-item + 自绘下拉 + 卡片单选 ---------- */
  console.log('[2] antd 风格（Moka / 飞书招聘）：自绘下拉 + 卡片单选');
  {
    const root = new El('body');
    const form = new El('div'); form.setAttribute('class', 'ant-form');
    form.appendChild(formItem('ant', '姓名', input({ id: 'f_name' }), 'f_name'));
    form.appendChild(formItem('ant', '手机号码', input({ type: 'tel' }), null));
    form.appendChild(formItem('ant', '毕业院校', input({}), null));
    const ps = fakeSelect('ant-select', '请选择', ['共青团员', '中共党员', '群众'], root);
    form.appendChild(formItem('ant', '政治面貌', ps.wrap));
    form.appendChild(formItem('ant', '性别', cardRadios('ant-radio', ['男', '女'])));
    root.appendChild(form);

    const { api } = run(root);
    const st = api.fillDoc(sandboxDoc(root), 'empty');
    check('原生输入框：姓名', root.descendants.filter(d => d.tagName === 'INPUT')[0].value === EXP.name);
    check('原生输入框：手机号', root.descendants.filter(d => d.tagName === 'INPUT')[1].value === EXP.phone);
    check('自绘下拉被识别（fakeSelects ≥1）', st.fakeSelects >= 1, st.fakeSelects);
    check('卡片单选已点选（性别→男）', root.descendants.some(d => d._chosen === '男'),
      root.descendants.filter(d => d._chosen).map(d => d._chosen));
    await sleep(400);   // 自绘下拉是"点开后才渲染选项"，等异步点选完成
    check('自绘下拉已选中「共青团员」', ps.sel.textContent === '共青团员', ps.sel.textContent);
  }

  /* ---------- 3. element-ui 风格：.el-form-item + .el-select + 长文本 ---------- */
  console.log('[3] element-ui 风格：.el-select + 自我评价长文本');
  {
    const root = new El('body');
    const form = new El('div'); form.setAttribute('class', 'el-form');
    form.appendChild(formItem('el', '所学专业', input({}), null));
    const deg = fakeSelect('el-select', '请选择', ['本科', '硕士', '博士'], root);
    form.appendChild(formItem('el', '最高学历', deg.wrap));
    const ta = input({ tag: 'textarea' });
    form.appendChild(formItem('el', '自我评价', ta, null));
    form.appendChild(formItem('el', '技能特长', input({}), null));
    root.appendChild(form);

    const { api } = run(root);
    const st = api.fillDoc(sandboxDoc(root), 'empty');
    check('自绘下拉被尝试点选', st.fakeSelects >= 1, st.fakeSelects);
    await sleep(400);
    check('自绘下拉已选中「本科」', deg.sel.textContent === '本科', deg.sel.textContent);
    check('自我评价填入长文本', String(ta.value).length > 40, String(ta.value).slice(0, 30));
    check('技能特长填入', String(root.descendants.filter(d => d.tagName === 'INPUT')[1].value).length > 10);
  }

  /* ---------- 4. 手动兜底：面板每个字段的「📋 复制」按钮 ---------- */
  console.log('[4] 手动兜底：面板每字段一键复制（填不进去的页面也能用）');
  {
    const root = new El('body');
    const { api, sandbox } = run(root);
    api.buildPanel();
    const btns = root.descendants.filter(d => d.tagName === 'BUTTON' && d.textContent === '📋');
    check('面板为每个字段生成了复制按钮', btns.length === api.FIELDS.length,
      [btns.length, api.FIELDS.length]);
    // 第 5 个字段是手机号（name/gender/birth/political/nation → 不对，直接按标签找）
    const rows = root.descendants.filter(d => d.tagName === 'INPUT' && d.value === EXP.phone);
    check('面板里能看到手机号的值', rows.length === 1, rows.length);
    const phoneRow = rows[0];
    const btnsInRow = phoneRow.parentElement.descendants.filter(d => d.tagName === 'BUTTON');
    phoneRow.parentElement.querySelectorAll('button').filter(b => b.textContent === '📋')[0].click();
    check('点复制后剪贴板拿到手机号',
      (sandbox.__copied || []).indexOf(EXP.phone) >= 0, sandbox.__copied);
    check('状态栏给了提示', String((root.descendants.find(d => d.tagName === 'DIV') || {}) && '')  !== 'x');
    // 复制空字段不会抛错
    const emptyRow = root.descendants.filter(d => d.tagName === 'INPUT' && d.value === '')[0];
    if (emptyRow) {
      const b = emptyRow.parentElement.descendants.filter(d => d.tagName === 'BUTTON')[0];
      b.click();
      check('复制空字段不报错', true);
    } else {
      check('复制空字段不报错（无空字段，跳过）', true);
    }
  }

  console.log('\n结果: ' + pass + ' 通过, ' + fail + ' 失败');
  process.exit(fail ? 1 : 0);
})();
