import {store} from '../stores/research.js';
import {runs} from '../api/research.js';
import {esc,fmt} from '../utils/format.js';
import {table} from '../components/common/table.js';
import {status} from '../components/common/status.js';
import {runList} from '../components/common/run-list.js';
import {download} from '../utils/download.js';

// 格图热图：颜色编码平均配对差方向，斑块描边，title 显示样本数
function heatmap(grid,patches){
  const {rows,cols,mean_diff,samples,patch_labels,valid_cells,threshold}=grid;
  const patchDir={};
  patches.forEach(p=>{p.cells.forEach(([r,c])=>{patchDir[`${r}-${c}`]=p.direction.startsWith('正')?'pos':'neg';});});
  let cells='';
  for(let r=0;r<rows;r++){
    for(let c=0;c<cols;c++){
      const v=mean_diff[r][c], n=samples[r][c], valid=valid_cells[r][c], pid=patch_labels[r][c];
      const dir=patchDir[`${r}-${c}`]||'';
      const cls=`cell ${!valid?'invalid':''} ${dir}`;
      const title=`(${r},${c}) 平均差=${v===null?'缺测':fmt(v)} 样本=${n}${pid?(' 斑块#'+pid):''}`;
      cells+=`<div class="${cls}" data-pid="${pid}" title="${esc(title)}"></div>`;
    }
  }
  return `<div class="heatmap" style="grid-template-columns:repeat(${cols},1fr)" role="img" aria-label="平均配对差格图，门槛${threshold}">${cells}</div>
  <div class="legend">
    <span><i class="sw pos"></i>正向越门槛斑块 (B−A&gt;+${fmt(threshold)})</span>
    <span><i class="sw neg"></i>负向越门槛斑块 (B−A&lt;−${fmt(threshold)})</span>
    <span><i class="sw invalid"></i>样本不足/缺测（每格需≥2张成对）</span>
  </div>`;
}

export async function render(id){
  if(!id)return `<h1>计算结果与解释</h1><p>选择一次运行查看冻结格图、斑块标注、校正 p 值与每格样本数。</p>${runList()}`;
  const r=await runs.get(id);
  store.runId=r.id;
  return `<div class="eyebrow">03 / RESULTS ARCHIVE · RUN ${r.id}</div>
  <h1>${esc(r.name)} ${status(r.status)}</h1>
  <div class="checksum">INPUT SHA256 ${r.checksum}</div>
  <p>快照 ${r.snapshot.length} 张纸样 · ${esc(r.created_at)} · ${r.review?'负责人已复核':'尚未复核'}</p>
  ${r.status==='failed'?`<div class="error">计算失败：${esc(r.error)}。请到来源页修复格图，然后创建新运行。</div>`
  :r.result?`<section class="result-intro"><strong>${esc(r.result.interpretation)}</strong><p>${esc(r.result.caveat)}</p></section>
    <h2>核心数值（含原平均色差分析）</h2>
    ${table(['业务指标','计算值'],Object.entries(r.result.metrics).map(([k,v])=>[k,fmt(v)]))}
    <h2>斑块标注与每格样本数 <small>颜色为平均配对差方向，描边格属四邻接同向斑块；悬停看每格样本数</small></h2>
    ${heatmap(r.result.grid,r.result.patches)}
    <h2>斑块明细 <small>共 ${r.result.patches.length} 个</small></h2>
    ${r.result.patches.length?table(['斑块编号','面积(格)','方向','斑块内最大平均差','格坐标(r,c)'],
      r.result.patches.map(p=>[p.patch_id,p.area,p.direction,fmt(p.mean_diff_max),
        p.cells.slice(0,12).map(x=>x.join(',')).join('；')+(p.cells.length>12?' …':'')]))
      :'<p class="method-note">当前门槛下没有越门槛的同向连通斑块。</p>'}
    <h2>${esc(r.result.table_title||'纸样配对概况')}</h2>
    ${table(r.result.columns,r.result.rows)}
    <div class="toolbar"><button id="export">下载核算 CSV（含斑块与每格样本数）</button>
    <a class="button secondary" href="#review/${r.id}">打开业务复核 →</a></div>`
  :'<p class="method-note">任务正在队列中。此页每2秒更新，结果写入数据库后展示。</p>'}
  <details><summary>本次冻结的门槛与纸样格图快照</summary><pre>${esc(JSON.stringify({parameters:r.parameters,snapshot:r.snapshot.map(s=>({source_key:s.source_key,angle:s.angle,rows:s.rows,cols:s.cols}))},null,2))}</pre></details>`;
}

export function bind(){
  const button=document.getElementById('export');
  if(button)button.onclick=async()=>{
    try{download(await runs.export(store.runId),'grid-run-'+store.runId+'.csv');}
    catch(e){document.getElementById('notice').textContent=e.message;}
  };
}
