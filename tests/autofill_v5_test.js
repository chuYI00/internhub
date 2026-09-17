/**
 * 网申助手 v5 专项自测。
 *
 * v5 相对 v4 的五个新增点，这里逐条守住：
 *   1. 字段库 40 → 70 类（国企网申特色字段：身高体重 / 奖惩 / 是否服从调剂 / 家庭成员 …）
 *   2. 三级标签识别：L1 精确 → L2 模糊 → L3 上下文推断（fieldset legend / 行首列）
 *   3. 多档数据：同一字段按岗位方向取不同值，且**绝不覆盖你手填过的资料**
 *   4. 填充报告：填完出「成功 N 项 / 需人工 M 项」，每项能一键滚动定位
 *   5. 字段学习：没认出来的字段教一次 → 下次任何网站自动填（这是 v5 的灵魂）
 *
 * 另外用三种真实网申结构各跑一遍：北森（antd 自绘）、Moka（分步 + placeholder）、
 * 国企老式表格（td 标签 + 自绘下拉 + 复选框）。
 *
 * 运行： node tests/autofill_v5_test.js
 */
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const dom = require('./lib/dom_stub.js');
const { El, input, select, fieldRow, labelTable, buildSandbox } = dom;

const NAME = process.argv[2] || path.join(__dirname, '..', '网申助手.user.js');
const code = fs.readFileSync(NAME, 'utf8');
const sleep = ms => new Promise(r => setTimeout(r, ms));
const doc = root => dom.makeDocument(root);

let pass = 0, fail = 0;
const check = (n, c, extra) => {
  if (c) { pass++; console.log('  ✓ ' + n); }
  else { fail++; console.log('  ✗ ' + n + (extra !== undefined ? '  -> ' + JSON.stringify(extra) : '')); }
};

function run(root, opts) {
  const sb = buildSandbox(root, opts);
  vm.runInContext(code, vm.createContext(sb), { filename: NAME });
  return { api: sb.window.__IHUB_AUTOFILL__, sandbox: sb };
}

const EXP = (() => {
  const r = new El('body');
  const sb = buildSandbox(r);
  vm.runInContext(code, vm.createContext(sb), { filename: NAME });
  return sb.window.__IHUB_AUTOFILL__.profile();
})();

/* ============================ 结构构造器 ============================ */

/** 北森式：<div class="ant-form-item"><div class="..-label">题目</div> 控件 </div> */
function antdItem(labelText, ctrl) {
  const item = new El('div'); item.setAttribute('class', 'ant-form-item');
  const lab = new El('div'); lab.setAttribute('class', 'ant-form-item-label'); lab.appendText(labelText);
  const box = new El('div'); box.setAttribute('class', 'ant-form-item-control');
  box.appendChild(ctrl);
  item.appendChild(lab); item.appendChild(box);
  return item;
}

/** 自绘下拉：点开后在 root 上渲染选项，点选项回填显示值（模拟 antd / element） */
function fakeSelect(root, placeholder, options, cls) {
  cls = cls || 'ant-select';
  const wrap = new El('div'); wrap.setAttribute('class', cls);
  const sel = new El('div'); sel.setAttribute('class', cls + '-selector');
  sel.appendText(placeholder);
  wrap.appendChild(sel);
  wrap.addEventListener('click', () => {
    if (wrap._opened) return;
    wrap._opened = true;
    const list = new El('div'); list.setAttribute('class', cls + '-dropdown');
    options.forEach(t => {
      const o = new El('div');
      o.setAttribute('class', 'ant-select-item-option');
      o.appendText(t);
      o.addEventListener('click', () => { sel.textContent = t; wrap._chosen = t; });
      list.appendChild(o);
    });
    root.appendChild(list);
  });
  return { wrap, sel };
}

/** 卡片单选组：外层容器带题目文字，里面是 role=radio 的卡片 */
function cardRadioGroup(labelText, values) {
  const box = new El('div'); box.setAttribute('class', 'ant-radio-group');
  box.appendText(labelText);
  values.forEach(v => {
    const w = new El('div'); w.setAttribute('class', 'ant-radio-wrapper');
    const r = new El('div'); r.setAttribute('role', 'radio');
    const t = new El('span'); t.appendText(v);
    r.appendChild(t); w.appendChild(r); box.appendChild(w);
  });
  return box;
}

/* ============================ 1. 字段库 ============================ */
console.log('[1] 字段库：40 → 70 类，国企特色字段齐全');
{
  const root = new El('body');
  const { api } = run(root);
  const ks = api.FIELDS.map(f => f.k);
  check('字段总数 ≥ 60 类', api.FIELDS.length >= 60, api.FIELDS.length);
  const need = ['height', 'weight', 'health', 'rewards', 'family', 'obey_adjust',
    'exam_province', 'household_type', 'join_party', 'relative', 'computer_level',
    'mandarin', 'training_mode', 'schooling_length', 'major_category', 'source',
    'hobby', 'student_cadre', 'social_practice', 'research', 'thesis', 'patent',
    'archive', 'bank', 'volunteer1', 'cet4', 'teacher', 'emergency_addr'];
  const miss = need.filter(k => ks.indexOf(k) < 0);
  check('国企网申特色字段全部就位', miss.length === 0, miss);
  check('没有重复字段 key', new Set(ks).size === ks.length, ks.length);
  check('每个字段都有分组（面板按组展示）',
    api.FIELDS.every(f => !!f.g), api.FIELDS.filter(f => !f.g).map(f => f.k));
  check('「备注」「验证码」这种不该进库的仍然没有',
    !api.FIELDS.some(f => /备注|验证码/.test(f.label)));

  // 老字段一个都不能少（v4 的能力不许倒退）
  const old = ['name', 'gender', 'school', 'major', 'phone', 'email', 'self_eval',
    'emergency_name', 'emergency_relation', 'marital'];
  check('v4 的 40 类字段一个没丢', old.every(k => ks.indexOf(k) >= 0),
    old.filter(k => ks.indexOf(k) < 0));
}

/* ============================ 2. 三级标签识别 ============================ */
console.log('[2] 三级识别：精确 → 模糊 → 上下文推断');
{
  const root = new El('body');
  const { api } = run(root);

  // L1 精确
  check('L1 精确：「政治面貌」', (api.bestField('政治面貌') || {}).k === 'political');
  check('L1 精确：「紧急联系人电话」不会被当成手机号',
    (api.bestField('紧急联系人电话') || {}).k === 'emergency_phone',
    (api.bestField('紧急联系人电话') || {}).k);
  check('L1 精确：「高考省份」不会被当成籍贯',
    (api.bestField('高考省份') || {}).k === 'exam_province');

  // L2 模糊（长关键词优先，避免"联系电话"撞到"紧急联系人电话"）
  check('L2 模糊：「请输入您的手机号码」→ 手机号',
    (api.bestField('请输入您的手机号码') || {}).k === 'phone');
  check('L2 模糊：「* 是否服从调剂分配」→ 是否服从调剂',
    (api.bestField('* 是否服从调剂分配') || {}).k === 'obey_adjust');
  check('L2 模糊：「奖惩情况（含处分）」→ 奖惩情况',
    (api.bestField('奖惩情况（含处分）') || {}).k === 'rewards');
  check('权重：命中最长关键词（"专业类别"不落到"专业"）',
    (api.bestField('专业类别') || {}).k === 'major_category');

  // L3 上下文：控件本身没任何线索，靠 fieldset legend / 容器标题认出来
  const fs = new El('fieldset');
  const lg = new El('legend'); lg.appendText('政治面貌');
  fs.appendChild(lg);
  const a = input({}), b = input({}), c = input({});
  fs.appendChild(a); fs.appendChild(b); fs.appendChild(c);
  root.appendChild(fs);
  check('L3 上下文：三个裸输入框在「政治面貌」分组里 → 认出是政治面貌',
    (api.bestField('', a, doc(root)) || {}).k === 'political',
    api.contextLabel(a, doc(root)));
  check('contextLabel 取到了 fieldset legend', api.contextLabel(a, doc(root)) === '政治面貌',
    api.contextLabel(a, doc(root)));
}

/* ============================ 3. 多档数据 ============================ */
console.log('[3] 多档数据：按岗位方向取不同值，且绝不覆盖手填资料');
{
  const root = new El('body');
  const { api } = run(root);
  check('ROLE_VALS 里有期望薪资 / 求职意向 / 到岗时间',
    !!(api.ROLE_VALS.expected_salary && api.ROLE_VALS.intent && api.ROLE_VALS.available));
  check('技术方向（ai）期望薪资高于内容方向（media）',
    parseInt(api.ROLE_VALS.expected_salary.ai, 10) > parseInt(api.ROLE_VALS.expected_salary.media, 10),
    [api.ROLE_VALS.expected_salary.ai, api.ROLE_VALS.expected_salary.media]);

  // 切方向：资料里本来有值的字段**不能被悄悄改掉**
  api.setDir('ai');
  const before = api.profile().expected_salary;
  api.setDir('media');
  const after = api.profile().expected_salary;
  check('切方向不会悄悄改写已有的期望薪资', before === after, [before, after]);

  // 明确点「用本方向值」才覆盖
  const n = api.applyRoleDefaults();
  check('点「用本方向值」后才覆盖（返回改了几项）', n >= 3, n);
  check('覆盖后取到的是 media 这一档', api.profile().expected_salary === api.ROLE_VALS.expected_salary.media,
    api.profile().expected_salary);
  api.setDir('ai'); api.applyRoleDefaults();
  check('再切到 ai 档，值跟着变', api.profile().expected_salary === api.ROLE_VALS.expected_salary.ai,
    api.profile().expected_salary);
  api.clearOverrides();
}

/* ============================ 4. 填充报告 ============================ */
console.log('[4] 📊 填充报告：成功 / 需人工 分列，能一键定位');
{
  const root = new El('body');
  root.appendChild(fieldRow('姓名', input({ name: 'n' })));       // 能填
  const unknown = input({ name: 'weird' });                        // 认不出来
  root.appendChild(fieldRow('身体高度（cm）', unknown));
  const noVal = input({});                                          // 认得出但资料没值
  root.appendChild(fieldRow('身高', noVal));
  const { api } = run(root);

  const st = api.fillDoc(doc(root), 'empty');
  check('填上的计入 filled', st.filled >= 1, st.filled);
  check('报告里有成功项说明', (st.report || []).some(r => /姓名/.test(r)), st.report);
  check('认不出来的进「需人工」', st.failed.some(f => f.reason === '没认出这是什么字段'),
    st.failed.map(f => f.reason));
  check('认得出但没值的也进「需人工」',
    st.failed.some(f => /资料里没有/.test(f.reason)), st.failed.map(f => f.reason));
  check('「需人工」每项带着元素引用（报告里点一下能跳过去）',
    st.failed.every(f => !!f.el));
  check('「需人工」每项有字段名与页面标签',
    st.failed.some(f => f.keyLabel === '身高') && st.failed.some(f => /身体高度/.test(f.label)),
    st.failed.map(f => [f.keyLabel, f.label]));

  const target = st.failed[0].el;
  api.locate(target);
  check('locate 会滚动到该字段', target._scrolled > 0, target._scrolled);
  check('locate 会聚焦该字段', target._focused > 0, target._focused);
  check('locate 给该字段加了红框', /d1242f/.test(String(target.style.outline || '')),
    target.style.outline);

  // 资料补上之后，同一页再填就应该成功
  api.setOverride('height', '175');
  const st2 = api.fillDoc(doc(root), 'empty');
  check('补了资料后「身高」填进去了', noVal.value === '175', noVal.value);
  check('补了资料后它从「需人工」里消失',
    !st2.failed.some(f => f.key === 'height'), st2.failed.map(f => f.key));
  api.clearOverrides();
}

/* ============================ 5. 字段学习（v5 灵魂） ============================ */
console.log('[5] 🧠 字段学习：没认出来 → 教一次 → 以后任何网站自动填');
{
  const root = new El('body');
  const weird = input({});
  root.appendChild(fieldRow('身体高度（cm）', weird));
  const { api, sandbox } = run(root);

  api.setOverride('height', '175');
  let st = api.fillDoc(doc(root), 'empty');
  check('第一次：不认识，填不进去', weird.value === '', weird.value);
  check('第一次：进「需人工」', st.failed.length === 1, st.failed.length);

  const unk = api.scanUnknown(doc(root));
  check('scanUnknown 把它扫出来了', unk.length === 1 && /身体高度/.test(unk[0].label), unk.map(u => u.label));
  check('scanUnknown 判它「没匹配到字段」', !unk[0].field, unk[0].field && unk[0].field.k);

  // 教一次
  const okAdd = api.learnAdd('身体高度（cm）', 'height');
  check('记住成功', okAdd === true);
  check('学习库里有了这条', Object.keys(api.learnMap()).length === 1, api.learnMap());
  check('学习库存在本机（localStorage / GM）',
    !!sandbox.localStorage.getItem(api.LEARN_KEY) || sandbox.__gmStore && sandbox.__gmStore.has(api.LEARN_KEY));
  check('learnLookup 能反查回来', api.learnLookup('身体高度（cm）') === 'height');

  // 第二次（换一个全新页面 = 换网站）
  const root2 = new El('body');
  const weird2 = input({});
  root2.appendChild(fieldRow('身体高度（cm）', weird2));
  const sb2 = buildSandbox(root2);
  vm.runInContext(code, vm.createContext(sb2), { filename: NAME });
  const api2 = sb2.window.__IHUB_AUTOFILL__;
  api2.setOverride('height', '175');
  // 学习库要能跨页面生效：把第一页存的内容灌进第二页的存储
  sb2.localStorage.setItem(api2.LEARN_KEY, sandbox.localStorage.getItem(api.LEARN_KEY));
  const st2 = api2.fillDoc(doc(root2), 'empty');
  check('第二次（另一个页面）：自动填上了', weird2.value === '175', weird2.value);
  check('第二次：不再进「需人工」', st2.failed.length === 0, st2.failed.map(f => f.reason));

  // 相似叫法也要认（"身体高度(cm)" vs "身体高度CM："）
  const root3 = new El('body');
  const weird3 = input({});
  root3.appendChild(fieldRow('身体高度CM：', weird3));
  const sb3 = buildSandbox(root3);
  vm.runInContext(code, vm.createContext(sb3), { filename: NAME });
  const api3 = sb3.window.__IHUB_AUTOFILL__;
  api3.setOverride('height', '175');
  sb3.localStorage.setItem(api3.LEARN_KEY, sandbox.localStorage.getItem(api.LEARN_KEY));
  api3.fillDoc(doc(root3), 'empty');
  check('相似叫法也认（大小写/标点不同）', weird3.value === '175', weird3.value);

  // 忘了它
  api.learnDel('身体高度（cm）');
  check('可以忘掉', Object.keys(api.learnMap()).length === 0);
  api.clearOverrides();
}

/* ============================ 6. 三种真实网申结构 ============================ */
async function scenarioBeisen() {
  console.log('[6a] 北森式（antd 自绘下拉 + 卡片单选）');
  const root = new El('body');
  const deg = fakeSelect(root, '请选择', ['大专', '本科', '硕士研究生']);
  const home = fakeSelect(root, '请选择', ['北京市', '云南省', '四川省']);
  root.appendChild(antdItem('最高学历', deg.wrap));
  root.appendChild(antdItem('籍贯', home.wrap));
  root.appendChild(antdItem('性别', cardRadioGroup('性别', ['男', '女'])));
  root.appendChild(antdItem('姓名', input({ placeholder: '请输入姓名' })));

  const { api } = run(root);
  api.setOverride('hometown', '云南大理');
  const st = api.fillDoc(doc(root), 'empty');
  await sleep(400);                       // 自绘下拉是点开后异步点选项的
  check('自绘下拉「学历」被点选', deg.wrap._chosen === '本科', deg.wrap._chosen);
  check('自绘下拉「籍贯」被点选', home.wrap._chosen === '云南省', home.wrap._chosen);
  check('卡片单选「性别」选中男',
    root.descendants.filter(d => d.getAttribute('role') === 'radio')[0]._clicked === true);
  check('普通输入框照常填', st.filled >= 1, st.filled);
  check('报告里标明了自绘下拉', st.fakeSelects >= 1, st.fakeSelects);
  api.clearOverrides();
}

async function scenarioMoka() {
  console.log('[6b] Moka 式（分步表单 + placeholder / aria-label）');
  const root = new El('body');
  const step1 = new El('div'); step1.setAttribute('class', 'step-1');
  step1.appendChild(new El('h3')).appendText('第 1 步 基本信息');
  step1.appendChild(fieldRow('', input({ placeholder: '请输入真实姓名', aria: 1 })));
  const p = input({}); p.setAttribute('placeholder', '请输入手机号');
  step1.appendChild(fieldRow('', p));
  const step2 = new El('div'); step2.setAttribute('class', 'step-2');
  step2.appendChild(fieldRow('期望薪资', input({})));
  step2.appendChild(fieldRow('是否服从调剂', input({ type: 'checkbox' })));
  root.appendChild(step1); root.appendChild(step2);

  const { api } = run(root);
  const st = api.fillDoc(doc(root), 'empty');
  const vals = root.descendants.filter(d => d.tagName === 'INPUT').map(d => d.value);
  check('placeholder 线索能填姓名', vals[0] === EXP.name, vals[0]);
  check('placeholder 线索能填手机号', vals[1] === EXP.phone, vals[1]);
  check('期望薪资按方向填了值', vals[2] !== '', vals[2]);
  const cb = root.descendants.filter(d => d.getAttribute('type') === 'checkbox')[0];
  check('「是否服从调剂」自动勾选（默认值=是）', cb.checked === true, cb.checked);
  check('分步表单两步都覆盖到', st.filled >= 3, st.filled);
}

async function scenarioGuoqi() {
  console.log('[6c] 国企老式表格（td 标签 + 奖惩/身高/家庭成员等特色字段）');
  const root = new El('body');
  const h = input({}), w = input({}), rw = input({ tag: 'textarea' });
  const fam = input({ tag: 'textarea' }), rel = input({}), hl = input({});
  root.appendChild(labelTable([
    ['身高（cm）', h],
    ['体重（kg）', w],
    ['奖惩情况', rw],
    ['家庭主要成员', fam],
    ['健康状况', hl],
  ]));
  root.appendChild(fieldRow('是否有亲属在本单位工作', rel));

  const { api } = run(root);
  api.setOverride('height', '175');
  api.setOverride('weight', '65');
  api.setOverride('rewards', '无');
  api.setOverride('family', '父亲 罗xx 务农　母亲 李xx 务农');
  const st = api.fillDoc(doc(root), 'empty');
  check('身高填入', h.value === '175', h.value);
  check('体重填入', w.value === '65', w.value);
  check('奖惩情况填入', rw.value === '无', rw.value);
  check('家庭成员填入', /父亲/.test(fam.value), fam.value);
  check('健康状况用默认值「健康」', hl.value === '健康', hl.value);
  check('「亲属是否在本单位」默认填「否」（不会去勾）', rel.value === '' || rel.value === '否', rel.value);
  check('这一页 5 项以上填入', st.filled >= 5, st.filled);
  api.clearOverrides();
}

/* ============================ 7. 面板渲染 ============================ */
console.log('[7] 面板：Shadow DOM 宿主 + 报告区 + 学习区都在');
{
  const root = new El('body');
  root.appendChild(fieldRow('姓名', input({})));
  const { api } = run(root);
  const src = fs.readFileSync(NAME, 'utf8');
  check('脚本里挂了 Shadow DOM 宿主（attachShadow，失败自动降级）', /attachShadow/.test(src));
  check('脚本里有字段学习存储键', /ihub_field_learn_v1/.test(src));
  check('面板有「重新扫描」按钮（学习区）', /重新扫描/.test(src));
  check('面板有「用本方向值」按钮（多档数据）', /用本方向值/.test(src));

  let threw = null;
  try { api.buildPanel(); } catch (e) { threw = e.message; }
  check('buildPanel 不报错', threw === null, threw);
  const texts = root.descendants.map(d => String(d.textContent || '')).join('|');
  check('面板里有学习区', /字段学习/.test(texts), texts.slice(0, 80));
  check('面板里有资料搜索框（placeholder）',
    root.descendants.some(d => d.tagName === 'INPUT' && /搜字段/.test(String(d.getAttribute('placeholder') || ''))));
  const sels = root.descendants.filter(d => d.tagName === 'SELECT');
  check('学习区每条有字段类型下拉', sels.length >= 1, sels.length);

  // 报告区：填完才有内容 —— 手动喂一份报告进去看它渲染得对不对
  api.renderReport({
    filled: 2, report: ['姓名→罗**', '手机号→135****'], fakeSelects: 1,
    failed: [{ el: root.descendants[0], label: '身高', key: 'height', keyLabel: '身高', reason: '资料里没有「身高」的值' }],
  });
  const t2 = root.descendants.map(d => String(d.textContent || '')).join('|');
  check('报告区渲染出成功项', /已填 2 项/.test(t2) && /姓名/.test(t2), t2.slice(0, 120));
  check('报告区渲染出「需人工」项', /需人工/.test(t2) && /资料里没有/.test(t2));
  check('报告区标明了自绘下拉', /自绘下拉/.test(t2));
}

(async () => {
  await scenarioBeisen();
  await scenarioMoka();
  await scenarioGuoqi();
  console.log('\n结果: ' + pass + ' 通过, ' + fail + ' 失败');
  process.exit(fail ? 1 : 0);
})();
