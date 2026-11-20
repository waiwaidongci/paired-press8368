import {DOMAIN} from '../constants/domain.js';
import {store,load} from '../stores/research.js';
import {runs} from '../api/research.js';
import {studySelect} from '../components/common/study-select.js';
import {runList} from '../components/common/run-list.js';
import {bindForm} from '../hooks/forms.js';
import {esc} from '../utils/format.js';

const {max_sheets,max_grid,enum_seconds}=DOMAIN.limits;

export function render(){
  const writable=localStorage.getItem('research-role')!=='viewer';
  return `<div class="eyebrow">02 / GRID METHOD WORKSHEET</div>
  <h1>${DOMAIN.field_label}</h1>
  <p class="lead">${DOMAIN.algorithm}</p>
  <div class="method-note">${DOMAIN.note}</div>
  <div class="strip"><span>容量上限 ${max_sheets} 张纸</span><span>每图 ≤ ${max_grid}×${max_grid} 格</span><span>全枚举限时 ${enum_seconds} 秒</span></div>
  ${writable?`<form id="run-form" class="worksheet">
    ${studySelect()}
    <label>本次研究名称<input name="name" required minlength="2" value="${esc(DOMAIN.names[0])} · 套印核算"></label>
    <div class="inline-form">
      <label>越门槛阈值 threshold（ΔE，&gt;0）<input name="threshold" type="number" step="any" min="0.0001" value="${DOMAIN.defaults.threshold}" required></label>
    </div>
    <p>提交时一次性冻结全部纸样的双工艺配对格图与门槛，生成 SHA256。排队后输入修改不会改写本运行；后台 worker 逐张整图符号翻转实算。</p>
    <button type="submit">冻结配对格图并排队计算 →</button>
  </form>`:'<p class="method-note">观察员可阅读研究记录，分析师与负责人可以发起计算。</p>'}
  <h2>计算记录</h2>${runList()}`;
}

export function bind(refresh){
  bindForm('run-form',async data=>{
    const parameters={threshold:+data.threshold};
    const r=await runs.create({study_id:+data.study_id,name:data.name,parameters});
    store.runId=r.id;await load();location.hash='results/'+r.id;
  });
  const sel=document.getElementById('study-select');
  if(sel)sel.onchange=()=>store.studyId=+sel.value;
}
