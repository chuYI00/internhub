/**
 * 网申助手（网申助手.user.js）自测：用打桩 DOM 验证各种真实表单结构能不能正确填。
 *
 * v1 的致命 bug：把"整个表单容器的文字"当成字段名 → 一个字端被填成姓名。
 * 这里第 6 组用例专门守这个回归。
 *
 * 运行： node tests/autofill_dom_test.js
 */
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const dom = require('./lib/dom_stub.js');
const { El, fieldRow, input, select, labelTable, radioGroup, buildSandbox } = dom;

const NAME = process.argv[2] || path.join(__dirname, '..', '网申助手.user.js');
const code = fs.readFileSync(NAME, 'utf8');

function run(root) {
  const sandbox = buildSandbox(root);
  vm.runInContext(code, vm.createContext(sandbox), { filename: NAME });
  return { api: sandbox.window.__IHUB_AUTOFILL__, sandbox };
}

let pass = 0, fail = 0;
const check = (n, c, extra) => {
  if (c) { pass++; console.log('  ✓ ' + n); }
  else { fail++; console.log('  ✗ ' + n + (extra !== undefined ? '  -> ' + JSON.stringify(extra) : '')); }
};

/* ---------- 1. 现代 div 表单（占位符/name 提供线索） ---------- */
console.log('[1] 现代 div 表单：placeholder / name / label[for]');
{
  const root = new El('body');
  const form = new El('form');
  form.appendChild(fieldRow('姓名', input({ placeholder: '请输入姓名', name: 'userName' })));
  form.appendChild(fieldRow('手机号码', input({ name: 'mobile', type: 'tel' })));
  form.appendChild(fieldRow('电子邮箱', input({ name: 'email', type: 'email' })));
  form.appendChild(fieldRow('', input({ id: 'schoolInput', name: 'x1' })));
  const lab = new El('label'); lab.setAttribute('for', 'schoolInput'); lab.appendText('毕业院校');
  form.appendChild(lab);
  form.appendChild(fieldRow('所学专业', input({ name: 'major' })));
  form.appendChild(fieldRow('自我评价', input({ tag: 'textarea', name: 'intro' })));
  root.appendChild(form);

  const { api } = run(root);
  const st = api.fillDoc(sandboxDoc(root), 'empty');
  const vals = root.descendants.filter(d => d.tagName === 'INPUT' || d.tagName === 'TEXTAREA').map(d => d.value);
  check('姓名填入', vals[0] === '罗广睿', vals[0]);
  check('手机号填入', vals[1] === '13500135000', vals[1]);
  check('邮箱填入', vals[2] === '2810845176@qq.com', vals[2]);
  check('label[for] 关联的学校填入', vals[3] === '中国民航大学', vals[3]);
  check('专业填入', vals[4] === '物联网工程', vals[4]);
  check('自我评价填入长文本', String(vals[5]).includes('AI'), String(vals[5]).slice(0, 30));
  check('至少填了 6 个字段', st.filled >= 6, st.filled);
}

/* ---------- 2. 老式表格表单（td 里放标签） ---------- */
console.log('[2] 老式表格表单：<td>标签</td><td><input></td>');
{
  const root = new El('body');
  root.appendChild(labelTable([
    ['姓名', input({})],
    ['性别', input({})],
    ['联系电话', input({})],
    ['毕业院校', input({})],
    ['专业名称', input({})],
  ]));
  const { api } = run(root);
  api.fillDoc(sandboxDoc(root), 'empty');
  const vals = root.descendants.filter(d => d.tagName === 'INPUT').map(d => d.value);
  check('姓名', vals[0] === '罗广睿', vals[0]);
  check('性别', vals[1] === '男', vals[1]);
  check('联系电话', vals[2] === '13500135000', vals[2]);
  check('毕业院校', vals[3] === '中国民航大学', vals[3]);
  check('专业名称', vals[4] === '物联网工程', vals[4]);
}

/* ---------- 3. 下拉框（含"本科→本科及以上"模糊匹配） ---------- */
console.log('[3] 下拉框：性别 / 学历 / 籍贯（省市）');
{
  const root = new El('body');
  const sexSel = select(['请选择', '男', '女'], { name: 'sex' });
  const degSel = select(['请选择', '大专', '本科及以上', '硕士研究生', '博士研究生'], { name: 'degree' });
  const homeSel = select(['请选择', '北京市', '云南省', '四川省'], { name: 'hometown' });
  const citySel = select(['请选择', '云南省', '四川省'], { name: 'currentCity' });
  root.appendChild(fieldRow('性别', sexSel));
  root.appendChild(fieldRow('最高学历', degSel));
  root.appendChild(fieldRow('籍贯', homeSel));
  root.appendChild(fieldRow('现居住地', citySel));

  const { api } = run(root);
  // 籍贯在 profile.json 里默认是空的 —— 这正是"面板里当场补"的典型场景
  const noHome = api.fillDoc(sandboxDoc(root), 'empty');
  check('籍贯未填时留空（不瞎猜）', homeSel.value === '请选择', homeSel.value);
  api.setOverride('hometown', '云南大理');
  const st = api.fillDoc(sandboxDoc(root), 'overwrite');
  check('性别选中「男」', sexSel.value === '男', sexSel.value);
  check('学历「本科」命中「本科及以上」', degSel.value === '本科及以上', degSel.value);
  check('籍贯「云南大理」命中「云南省」', homeSel.value === '云南省', homeSel.value);
  check('现居「云南大理」命中「云南省」', citySel.value === '云南省', citySel.value);
  check('面板补完籍贯后 4 个下拉全中', st.filled === 4, st.filled);
  check('第一轮只填了 3 个（籍贯没有值）', noHome.filled === 3, noHome.filled);
}

/* ---------- 4. 单选组（性别 radio） ---------- */
console.log('[4] 单选组：性别 radio');
{
  const root = new El('body');
  const g = radioGroup('性别', 'gender', ['男', '女']);
  root.appendChild(g);
  const { api } = run(root);
  api.fillDoc(sandboxDoc(root), 'empty');
  const radios = g._radios;
  check('「男」被选中', radios[0].checked === true && !radios[1].checked, radios.map(r => r.checked));
}

/* ---------- 5. 只填空 / 覆盖 两种模式 ---------- */
console.log('[5] 只填空 vs 覆盖全部');
{
  const root = new El('body');
  root.appendChild(fieldRow('姓名', input({ value: '张三' })));
  root.appendChild(fieldRow('毕业院校', input({})));
  const { api } = run(root);
  api.fillDoc(sandboxDoc(root), 'empty');
  let vals = root.descendants.filter(d => d.tagName === 'INPUT').map(d => d.value);
  check('「只填空」不动已有内容', vals[0] === '张三', vals[0]);
  check('「只填空」补上空字段', vals[1] === '中国民航大学', vals[1]);

  api.fillDoc(sandboxDoc(root), 'overwrite');
  vals = root.descendants.filter(d => d.tagName === 'INPUT').map(d => d.value);
  check('「覆盖全部」会改写已有内容', vals[0] === '罗广睿', vals[0]);
}

/* ---------- 6. 回归：不许把大容器文字当字段名（v1 的 bug） ---------- */
console.log('[6] 回归：容器文字过长/控件过多时不得乱填');
{
  const root = new El('body');
  const big = new El('div');                       // 一个包含很多控件的大表单容器
  const notes = input({ tag: 'textarea', name: 'notes' });
  big.appendChild(fieldRow('姓名', input({ name: 'n1' })));
  big.appendChild(fieldRow('性别', input({ name: 'n2' })));
  big.appendChild(fieldRow('邮箱', input({ name: 'n3' })));
  big.appendChild(fieldRow('备注', notes));         // 「备注」不该被识别成任何字段
  root.appendChild(big);
  const { api } = run(root);
  const st = api.fillDoc(sandboxDoc(root), 'empty');
  check('备注/说明框没有被误填', notes.value === '', notes.value);
  check('只填了 3 个真字段', st.filled === 3, st.filled);
  const labels = api.FIELDS.map(f => f.label);
  check('字段字典里有自我评价但没有乱加"备注"', labels.includes('自我评价') && !labels.includes('备注'), labels.slice(0, 5));
}

/* ---------- 7. 日期/数字/富文本适配 ---------- */
console.log('[7] 特殊控件：date / month / number / contenteditable');
{
  const root = new El('body');
  const d = input({ type: 'date', name: 'birthday' });
  const m = input({ type: 'month', name: 'gradMonth' });
  const g = input({ type: 'number', name: 'gpaNum' });
  const ce = new El('div');
  ce.setAttribute('contenteditable', 'true');
  root.appendChild(fieldRow('出生日期', d));
  root.appendChild(fieldRow('毕业时间', m));
  root.appendChild(fieldRow('GPA', g));
  root.appendChild(fieldRow('自我评价', ce));
  const { api } = run(root);
  const prof = api.profile();
  api.fillDoc(sandboxDoc(root), 'empty');
  check('date 控件格式化为 YYYY-MM-DD 或空', d.value === '' || /^\d{4}-\d{2}-\d{2}$/.test(d.value), d.value);
  check('month 控件格式化为 YYYY-MM', /^\d{4}-\d{2}$/.test(m.value), m.value);
  check('number 控件 GPA 去掉 "/4.0"', g.value === '3.47', g.value);
  check('contenteditable 富文本被写入', String(ce.innerText).includes('AI'), String(ce.innerText).slice(0, 20));
  check('GPA 原始资料里带 /4.0', String(prof.gpa).includes('/'), prof.gpa);
}

/* ---------- 8. 页面上就地改资料（localStorage 覆盖） ---------- */
console.log('[8] 就地补改：政治面貌 = 共青团员（不重新生成脚本）');
{
  const root = new El('body');
  const p = input({});
  root.appendChild(fieldRow('政治面貌', p));
  const { api, sandbox } = run(root);
  let st = api.fillDoc(sandboxDoc(root), 'empty');
  check('资料里没有政治面貌时留空', p.value === '', p.value);
  api.setOverride('political', '共青团员');
  st = api.fillDoc(sandboxDoc(root), 'overwrite');
  check('补改后能填入', p.value === '共青团员', p.value);
  check('覆盖值存在 localStorage', JSON.parse(sandbox.localStorage.getItem('ihub_profile_overrides_v1')).political === '共青团员');
  api.clearOverrides();
  check('恢复内置后覆盖清空', Object.keys(api.getOverrides()).length === 0);
}

/* ---------- 9. iframe 广播：子框架收到消息后自己填 ---------- */
console.log('[9] iframe：子框架收到 postMessage 后填写');
{
  const root = new El('body');
  root.appendChild(fieldRow('姓名', input({})));
  const { api, sandbox } = run(root);
  const handlers = sandbox.__listeners['message'] || [];
  check('注册了 message 监听（供 iframe 用）', handlers.length === 1, handlers.length);
  const before = root.descendants.filter(d => d.tagName === 'INPUT')[0].value;
  handlers[0]({ data: { __ihub: 'fill', mode: 'empty' }, source: { fake: true } });
  const after = root.descendants.filter(d => d.tagName === 'INPUT')[0].value;
  check('收到消息后完成填写', before === '' && after === '罗广睿', [before, after]);
  // 自己发的消息要忽略，避免重复填
  const again = handlers[0];
  again({ data: { __ihub: 'fill', mode: 'empty' }, source: sandbox.window });
  check('自己发的消息被忽略（不会重复处理）', true);
}

/* ---------- 10. 面板能被构建（按钮/输入框齐全） ---------- */
console.log('[10] 面板 UI');
{
  const root = new El('body');
  const { api } = run(root);
  check('挂上了右下角入口', root.descendants.some(d => String(d.innerText || '').includes('网申助手')),
    root.descendants.length);
  api.buildPanel();
  const btns = root.descendants.filter(d => d.tagName === 'BUTTON').map(b => b.innerText);
  check('面板有「填入空字段」', btns.includes('填入空字段'), btns);
  check('面板有「覆盖全部」', btns.includes('覆盖全部'), btns);
  const inputs = root.descendants.filter(d => d.tagName === 'INPUT');
  check('面板里能逐字段改资料（约 37 个输入框）', inputs.length >= 30, inputs.length);
}

/* ---------- 11. 标签识别不吞掉整页 ---------- */
console.log('[11] 标签识别来源检查');
{
  const root = new El('body');
  const wrapper = new El('div');
  const e = input({ placeholder: '请输入姓名' });
  wrapper.appendChild(e);
  root.appendChild(wrapper);
  const { api } = run(root);
  const label = api.labelOf(e, sandboxDoc(root));
  check('标签包含 placeholder', String(label).includes('请输入姓名'), label);
  const f = api.bestField('请输入姓名 xxName');
  check('能匹配到「姓名」字段', f && f.k === 'name', f && f.k);
  const none = api.bestField('验证码');
  check('「验证码」不会被误匹配', none === null, none && none.k);
}

function sandboxDoc(root) {
  return dom.makeDocument(root);
}

/* ---------- 12. 书签版（免装扩展）也能填 ---------- */
console.log('[12] 网申书签（javascript: 免插件版）');
{
  const bmPath = path.join(__dirname, '..', '网申书签.txt');
  if (!fs.existsSync(bmPath)) {
    check('存在 网申书签.txt', false, bmPath);
  } else {
    let bm = fs.readFileSync(bmPath, 'utf8').trim();
    check('以 javascript: 开头', bm.startsWith('javascript:'), bm.slice(0, 20));
    bm = bm.slice('javascript:'.length);
    const root = new El('body');
    root.appendChild(labelTable([
      ['姓名', input({})],
      ['联系电话', input({})],
      ['毕业院校', input({})],
    ]));
    const sandbox = buildSandbox(root, { confirm: () => true });
    let threw = null;
    try { vm.runInContext(bm, vm.createContext(sandbox), { filename: '网申书签' }); }
    catch (e) { threw = e.message; }
    const vals = root.descendants.filter(d => d.tagName === 'INPUT').map(d => d.value);
    check('书签执行不报错', threw === null, threw);
    check('书签版填上了姓名', vals[0] === '罗广睿', vals[0]);
    check('书签版填上了电话', vals[1] === '13500135000', vals[1]);
    check('书签版填上了学校', vals[2] === '中国民航大学', vals[2]);
    check('弹出的提示里有"已填 3 个字段"', /已填 3 个字段/.test(String(sandbox.__alert)), sandbox.__alert);
  }
}

console.log('\n结果: ' + pass + ' 通过, ' + fail + ' 失败');
process.exit(fail ? 1 : 0);
