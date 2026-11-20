import {DOMAIN} from '../constants/domain.js';
import {store,load,loadRows} from '../stores/research.js';
import {studies} from '../api/research.js';
import {studySelect} from '../components/common/study-select.js';
import {table} from '../components/common/table.js';
import {esc} from '../utils/format.js';
import {bindForm} from '../hooks/forms.js';

const {max_sheets,max_grid}=DOMAIN.limits;

// 把 TSV/CSV 文本解析成二维数组；空单元格记为缺测(null)
function parseGrid(text){
  const lines=text.replace(/\r/g,'').split('\n').filter(l=>l.trim()!=='');
  if(!lines.length) throw new Error('格图内容为空');
  const width=lines[0].split(/\t|,/).length;
  return lines.map(line=>{
    const cells=line.split(/\t|,/);
    if(cells.length!==width) throw new Error('格图各行列数不一致');
    return cells.map(c=>{
      const t=c.trim();
      if(t===''||t.toLowerCase()==='na'||t==='-') return null;
      const v=Number(t);
      if(!Number.isFinite(v)) throw new Error('格值必须为数值，空/NA/- 表示缺测');
      return v;
    });
  });
}

function sheetForm(){
  return `<details id="sheet-details"><summary id="sheet-summary">补传纸样双工艺格图（同版两侧齐备才一次性对齐）</summary>
  <form id="row-form" class="grid-form">
    <div class="inline-form">
      <label>纸样编号<input name="source_key" placeholder="如 SHEET-001" required></label>
      <label>定位角<select name="angle">${[0,90,180,270].map(a=>`<option value="${a}">${a}°</option>`).join('')}</select></label>
    </div>
    <p class="hint">每版粘贴 TSV/CSV 矩形格图（≤${max_grid}×${max_grid}）；两版行列必须一致。空格、NA、- 表示该格缺测，缺测不补值。</p>
    <div class="grid-editors">
      ${DOMAIN.processes.map(([key,label])=>`<label class="grid-editor">${esc(label)}<textarea name="grid_${key}" rows="8" spellcheck="false" placeholder="行内用 Tab 或逗号分隔，换行表示下一行"></textarea></label>`).join('')}
    </div>
    <button type="submit">保存对齐格图</button>
    <button type="button" id="cancel-edit" hidden>取消编辑</button>
  </form></details>`;
}

export async function render(){
  await loadRows();
  const writable=localStorage.getItem('research-role')!=='viewer';
  const full=store.rows.length>=max_sheets;
  return `<div class="eyebrow">01 / GRID REGISTER</div>
  <h1>${DOMAIN.study_label}与${DOMAIN.row_label}</h1>
  <p>${DOMAIN.note}</p>
  <div class="toolbar">${studySelect()}<span class="cap-badge">${store.rows.length}/${max_sheets} 张 · 每图 ≤ ${max_grid}×${max_grid}</span></div>
  ${writable?`<details><summary>新增${DOMAIN.study_label}</summary>
    <form id="study-form" class="inline-form">
      <label>名称<input name="name" required minlength="2"></label>
      <label>来源文件<input name="source_filename" value="grid-notes-202611.csv" required></label>
      <label>说明<input name="description"></label>
      <button type="submit">保存批次</button>
    </form></details>
    <h2 id="row-heading">分版补传格图</h2>
    ${full?`<div class="error">已达容量上限 ${max_sheets} 张，拒绝继续排队/录入。</div>`:sheetForm()}`:''}
  <h2>纸样格图明细 <small>${store.rows.length} 张 · 运行后更改不会改写历史快照</small></h2>
  ${table(['纸样编号','定位角','格图尺寸','工艺A缺测','工艺B缺测',...(writable?['操作']:[])],
    store.rows.map(row=>{
      const miss=proc=>row.grids[proc].reduce((n,line)=>n+line.filter(c=>c===null).length,0);
      return [row.source_key,row.angle+'°',`${row.rows}×${row.cols}`,miss('a'),miss('b'),
        ...(writable?[{html:`<button class="text" data-edit="${row.id}">编辑</button> <button class="text" data-delete="${row.id}">移除</button>`}]:[])];
    }))}`;
}

function toTSV(grid){return grid.map(line=>line.map(c=>c===null?'':c).join('\t')).join('\n');}

export function bind(refresh){
  let editing=null;
  const sel=document.getElementById('study-select');
  if(sel)sel.onchange=()=>{store.studyId=+sel.value;refresh();};
  bindForm('study-form',async data=>{const s=await studies.create(data);store.studyId=s.id;await load();refresh();});
  bindForm('row-form',async data=>{
    let grids;
    try{
      grids={a:parseGrid(data.grid_a),b:parseGrid(data.grid_b)};
    }catch(e){document.getElementById('notice').textContent=e.message;return;}
    const payload={source_key:data.source_key,angle:Number(data.angle),grids};
    await studies.save(store.studyId,payload,editing);
    await load();refresh();
  });
  document.querySelectorAll('[data-edit]').forEach(el=>el.onclick=()=>{
    const row=store.rows.find(r=>r.id===+el.dataset.edit);
    editing=row.id;
    const details=document.getElementById('sheet-details');if(details)details.open=true;
    const form=document.getElementById('row-form');
    form.elements.source_key.value=row.source_key;
    form.elements.angle.value=row.angle;
    form.elements.grid_a.value=toTSV(row.grids.a);
    form.elements.grid_b.value=toTSV(row.grids.b);
    document.getElementById('sheet-summary').textContent='编辑 '+row.source_key;
    document.getElementById('cancel-edit').hidden=false;
    form.scrollIntoView({behavior:'smooth',block:'center'});
  });
  const cancel=document.getElementById('cancel-edit');
  if(cancel)cancel.onclick=()=>refresh();
  document.querySelectorAll('[data-delete]').forEach(el=>el.onclick=async()=>{
    try{await studies.remove(store.studyId,+el.dataset.delete);await load();refresh();}
    catch(e){document.getElementById('notice').textContent=e.message;}
  });
}
