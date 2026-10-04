'use strict';
titles.pipeline=['پایپ‌لاین زنده','مسیر اجرا، ورودی، خروجی و خطای هر مرحله؛ به‌روزرسانی خودکار'];
titles.codeknowledge=['مدیریت دانش کد','گره، رابطه و برداشت از کد را در نسخه کاری مدیریت و سپس منتشر کنید'];
const nav=document.querySelector('.nav');
for(const [tab,label,icon] of [['codeknowledge','مدیریت دانش کد','✎'],['pipeline','پایپ‌لاین زنده','⇢']]){
  const button=el('button');button.dataset.tab=tab;button.append(el('span',icon,'icon'),document.createTextNode(label));
  button.onclick=()=>navigate(tab);nav.insertBefore(button,nav.querySelector('[data-tab="traces"]'));
}
const style=el('style',`
.pipeline-canvas{background-color:#f8fafc;background-image:radial-gradient(#d0d8e4 1px,transparent 1px);background-size:18px 18px;overflow:auto;border:1px solid #dbe3ee;border-radius:12px;direction:ltr;padding:20px 8px}
.pipeline-canvas svg{min-width:1040px;width:100%;height:245px}
.pipe-node{cursor:pointer;outline:none}.pipe-node rect{fill:white;stroke:#cbd5e1;stroke-width:1.5}.pipe-node text{font:12px Tahoma;fill:#334155}.pipe-node.running rect{stroke:#4f46e5;stroke-width:3;fill:#eef2ff;animation:pipeGlow 1s infinite}.pipe-node.passed rect{stroke:#159574;fill:#eaf9f3}.pipe-node.failed rect{stroke:#dc4560;fill:#fff0f2}.pipe-node.skipped{opacity:.5}.pipe-edge{stroke:#c7d2e2;stroke-width:2;fill:none}.pipe-edge.active{stroke:#6366f1;stroke-dasharray:6 5;animation:pipeTravel .6s linear infinite}.pipe-edge.passed{stroke:#159574}
@keyframes pipeTravel{to{stroke-dashoffset:-22}}@keyframes pipeGlow{50%{stroke-opacity:.5}}.checkline{display:flex;gap:10px;align-items:center;line-height:1.8;font-weight:normal}.checkline input{width:auto}.danger{background:#fff0f2;color:#ba3854}.editor-actions{position:sticky;bottom:0;background:white;padding:14px 0;margin-top:14px;border-top:1px solid #e3e9f2}.select-list{max-height:650px;overflow:auto}.published-pill{margin-left:8px}
`);document.head.append(style);
function editorField(key,label,value,kind='input'){
  const wrap=el('div',undefined,'formfield'),input=el(kind);input.value=value??'';input.id='editor-'+key;
  const title=el('label',label);title.htmlFor=input.id;
  if(kind==='textarea')input.rows=key==='content'?16:4;
  wrap.append(title,input);return {wrap,input};
}
function toggle(label,value){const l=el('label',undefined,'checkline'),input=el('input');input.type='checkbox';input.checked=value;l.append(input,document.createTextNode(label));return {wrap:l,input};}
function confirmation(title,description,yes){
  const dialog=el('dialog');dialog.style.cssText='border:1px solid #d7dfed;border-radius:14px;max-width:500px;padding:25px';
  dialog.append(el('h2',title),el('p',description));const bar=el('div',undefined,'toolbar');
  bar.append(btn('انصراف',()=>{dialog.close();dialog.remove()},'ghost'),btn('حذف از نسخه کاری',async()=>{dialog.close();dialog.remove();await yes()},'danger'));
  dialog.append(bar);document.body.append(dialog);dialog.showModal();
}
function draftBar(parent,data){
  const bar=el('div',undefined,'toolbar');bar.append(badge(data.dirty?'تغییر منتشرنشده':'نسخه کاری با منتشرشده یکسان است',data.dirty?'warn':'green'));
  const publish=btn('انتشار دانش برای چت',async()=>{const job=await api('jobs','POST',{kind:'publish-knowledge',version:data.draftVersion});state.publishJob=job.id;state.pipelineMode='publication';await navigate('pipeline')},'');
  bar.append(publish,el('span','نسخه کاری: '+data.draftVersion.slice(0,12),'mono'));parent.append(bar);
  parent.append(el('p','ذخیره و حذف، نسخه کاری را تغییر می‌دهند. چت فقط نسخه منتشرشده را مصرف می‌کند. تاریخچه تغییرات حفظ می‌شود.','muted'));
}
renderers.knowledge=async()=>{
  const data=await api('knowledge');if(state.tab!=='knowledge')return;const c=$('content');c.replaceChildren();draftBar(c,data);
  const grid=el('div',undefined,'grid2'),list=box('اسناد نسخه کاری'),editor=box('ویرایش سند'),search=el('input'),items=el('div',undefined,'list select-list');
  search.placeholder='جست‌وجوی نام سند';search.setAttribute('aria-label','جست‌وجوی سند');
  const upload=el('input');upload.type='file';upload.accept='.md,text/markdown';upload.classList.add('hidden');upload.setAttribute('aria-label','بارگذاری راهنمای Markdown');
  upload.onchange=async()=>{const file=upload.files[0];if(!file)return;if(file.size>200000){toast('فایل باید کمتر از ۲۰۰ کیلوبایت باشد.');return}edit(null);$('editor-name').value=file.name;$('editor-content').value=await file.text()};
  list.append(btn('افزودن سند راهنما',()=>edit(null),''),btn('واردکردن فایل Markdown',()=>upload.click()),upload,el('div',undefined,'divider'),search,items);grid.append(list,editor);c.append(grid);
  function edit(doc){
    editor.replaceChildren(el('h2',doc?'ویرایش '+doc.name:'سند جدید'));
    const fields={};
    for(const [key,label,value,kind] of [['name','نام فایل (مثل MyGuide.md)',doc?.name??'','input'],['keywords','کلمات موضوع برای بازیابی (با ویرگول جدا کنید)',doc?.keywords?.join('، ')??'','input'],['content','متن Markdown راهنما',doc?.content??'# عنوان راهنما\n\n','textarea']]){
      const field=editorField(key,label,value,kind);fields[key]=field.input;editor.append(field.wrap);
    }
    fields.name.disabled=!!doc;fields.name.dir='ltr';
    const enabled=toggle('این سند در دانش منتشرشده فعال باشد',doc?.enabled??true);
    const external=toggle('اجازه ارسال متن این سند به Gemini برای پاسخ‌گویی را می‌دهم',doc?.externalEligible??false);
    editor.append(enabled.wrap,external.wrap,el('p','برای سند جدید یا متن ویرایش‌شده، محتوای مجاز راهنما را وارد کنید. کد خام را در بخش دانش کد نگه دارید. بدون اجازه مدل، متن سند فقط محلی نمایش داده می‌شود.','muted'));
    // A content change must renew consent, rather than inheriting the seed document permission silently.
    fields.content.oninput=()=>{external.input.checked=false};
    const actions=el('div',undefined,'toolbar editor-actions');
    actions.append(btn('ذخیره در نسخه کاری',async()=>{
      const name=fields.name.value.trim(),value={content:fields.content.value,keywords:fields.keywords.value.split(/[,،\n]/).map(k=>k.trim()).filter(Boolean),enabled:enabled.input.checked,externalEligible:external.input.checked};
      await api('knowledge/documents/'+encodeURIComponent(name),doc?'PUT':'POST',{version:data.draftVersion,value});toast('سند در نسخه کاری ذخیره شد؛ برای اثر در چت آن را منتشر کنید.');await navigate('knowledge');
    },''));
    if(doc)actions.append(btn('حذف سند',()=>confirmation('حذف '+doc.name,'این سند از نسخه کاری حذف می‌شود؛ تاریخچه و نسخه اصلی حفظ می‌شوند. حذف در چت پس از انتشار اثر می‌گذارد.',async()=>{await api('knowledge/documents/'+encodeURIComponent(doc.name),'DELETE',{version:data.draftVersion});await navigate('knowledge')}),'danger'));
    editor.append(actions);
    if(doc)showData(editor,'نسخه و مشخصات سند',{sha256:doc.sha256,lines:doc.lines,reviewStatus:doc.reviewStatus});
  }
  function draw(){items.replaceChildren();for(const doc of data.documents.filter(d=>d.name.toLowerCase().includes(search.value.toLowerCase()))){const b=el('button',undefined,'item');b.append(el('div',doc.name),el('small',(doc.enabled?'فعال':'غیرفعال')+' · '+(doc.externalEligible?'مجاز برای مدل':'فقط محلی'),'muted'));b.onclick=()=>edit(doc);items.append(b)}}
  search.oninput=draw;draw();edit(data.documents[0]??null);
};

renderers.codeknowledge=async()=>{
  const data=await api('knowledge');if(state.tab!=='codeknowledge')return;const c=$('content');c.replaceChildren();draftBar(c,data);
  c.append(el('div','مدیریت دانش استخراج‌شده و یادداشت‌هاست. متن سورس، خط و هش شاهد اصلی قابل بازنویسی نیستند. برداشت و رابطه ویرایش‌شده inferred و pending-human می‌شوند.','notice'));
  const grid=el('div',undefined,'grid2'),list=box('موجودیت‌های دانش کد'),editor=box('ویرایش موجودیت'),pick=el('select'),items=el('div',undefined,'list select-list');
  for(const [value,label] of [['nodes','گره‌ها: مسیر، فرم، API و ...'],['edges','روابط گراف'],['observations','شواهد و یادداشت‌های کد']]){const option=el('option',label);option.value=value;pick.append(option)}
  pick.setAttribute('aria-label','نوع موجودیت دانش کد');list.append(pick,el('div',undefined,'divider'),btn('افزودن موجودیت',()=>edit(null),''),items);grid.append(list,editor);c.append(grid);
  pick.value=state.graphCollection??'nodes';
  function edit(item){
    const collection=pick.value;editor.replaceChildren(el('h2',item?'ویرایش '+item.id:'موجودیت جدید'));const fields={};
    const definitions=[['id','شناسه انگلیسی ثابت',item?.id??'','input']];
    if(collection==='nodes')definitions.push(['kind','نوع گره (route / form / api / ...)',item?.kind??'form','input'],['label','عنوان قابل نمایش',item?.label??'','input']);
    else if(collection==='edges')definitions.push(['from','شناسه گره مبدأ',item?.from??'','input'],['to','شناسه گره مقصد',item?.to??'','input'],['relation','نوع رابطه (مثلاً calls)',item?.relation??'calls','input'],['evidenceIds','شناسه شواهد (با ویرگول)',item?.evidenceIds?.join(', ')??'','input']);
    else definitions.push(['statementFa','برداشت فارسی یا یادداشت درباره کد',item?.statementFa??'','textarea']);
    for(const [key,label,value,kind] of definitions){const f=editorField(key,label,value,kind);fields[key]=f.input;editor.append(f.wrap)}fields.id.disabled=!!item;fields.id.dir='ltr';
    const actions=el('div',undefined,'toolbar editor-actions');actions.append(btn('ذخیره موجودیت',async()=>{
      const value={};for(const [key,input] of Object.entries(fields))if(key!=='id')value[key]=key==='evidenceIds'?input.value.split(/[,،\n]/).map(k=>k.trim()).filter(Boolean):input.value;
      await api('knowledge/graph/'+collection+'/'+encodeURIComponent(fields.id.value.trim()),item?'PUT':'POST',{version:data.draftVersion,value});toast('ذخیره شد؛ نسخه کاری نیازمند انتشار است.');await navigate('codeknowledge');
    },''));
    if(item)actions.append(btn('حذف موجودیت',()=>confirmation('حذف '+item.id,'حذف گره روابط وابسته را هم از نسخه کاری حذف می‌کند. حذف شاهد، ارجاعات و روابط بدون شاهد را حذف می‌کند. سورس اصلی حفظ می‌شود.',async()=>{await api('knowledge/graph/'+collection+'/'+item.id,'DELETE',{version:data.draftVersion});await navigate('codeknowledge')}),'danger'));
    editor.append(actions);if(item)showData(editor,'منبع، سطح حقیقت و داده ثبت‌شده',item);
  }
  function draw(){items.replaceChildren();for(const item of data.graph[pick.value]){const b=el('button',undefined,'item');b.append(el('div',item.label||item.statementFa||[item.from,item.relation,item.to].filter(Boolean).join(' → ')||item.id),el('small',item.id+' · '+(item.truthLevel||item.kind),'muted'));b.onclick=()=>edit(item);items.append(b)}edit(data.graph[pick.value][0]??null)}
  pick.onchange=()=>{state.graphCollection=pick.value;draw()};draw();
};

function drawPipeline(container,nodes){
  container.replaceChildren();const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');
  const fullWidth=Math.max(1080,nodes.length*156),scale=state.pipeZoom??Math.min(1,Math.max(720,container.clientWidth-20)/fullWidth);
  svg.setAttribute('viewBox','0 0 '+fullWidth+' 220');svg.style.minWidth='0';svg.style.width=fullWidth*scale+'px';svg.style.height=220*scale+'px';
  nodes.forEach((node,i)=>{
    const x=20+i*156,y=i%2?88:42;
    if(i){const previous=nodes[i-1],px=20+(i-1)*156,py=(i-1)%2?88:42,line=document.createElementNS(ns,'path');line.setAttribute('d',`M ${px+132} ${py+39} C ${px+155} ${py+39}, ${x-24} ${y+39}, ${x} ${y+39}`);line.classList.add('pipe-edge');if(node.status==='running')line.classList.add('active');else if(node.status==='passed')line.classList.add('passed');svg.append(line)}
    const group=document.createElementNS(ns,'g'),rect=document.createElementNS(ns,'rect'),label=document.createElementNS(ns,'text'),status=document.createElementNS(ns,'text');
    group.classList.add('pipe-node',node.status);group.setAttribute('tabindex','0');group.setAttribute('role','button');group.setAttribute('aria-label',node.label+' '+node.status);
    rect.setAttribute('x',x);rect.setAttribute('y',y);rect.setAttribute('width','132');rect.setAttribute('height','80');rect.setAttribute('rx','12');
    label.setAttribute('x',x+66);label.setAttribute('y',y+29);label.setAttribute('text-anchor','middle');label.textContent=node.label;
    status.setAttribute('x',x+66);status.setAttribute('y',y+55);status.setAttribute('text-anchor','middle');status.style.fontSize='10px';status.textContent=({pending:'منتظر',running:'در حال اجرا',passed:'انجام شد',failed:'خطا',skipped:'اجرا نشد'})[node.status]||node.status;
    group.append(rect,label,status);group.onclick=()=>inspectPipelineNode(node);group.onkeydown=e=>{if(e.key==='Enter')inspectPipelineNode(node)};svg.append(group);
  });container.append(svg);
}
function inspectPipelineNode(node){const detail=$('pipeline-detail');if(!detail)return;detail.replaceChildren(el('h2',node.label),badge(statusLabel(node.status),node.status==='passed'?'green':'warn'));if(node.started_ms!==undefined)detail.append(el('p','شروع: '+node.started_ms+' ms · پایان: '+(node.ended_ms??'در حال اجرا'),'mono'));showData(detail,'ورودی و خروجی ثبت‌شدهٔ این مرحله',node.details??{});}
renderers.pipeline=async()=>{
  const c=$('content');c.replaceChildren();const controls=box('اجرای قابل مشاهده'),question=el('input'),mode=el('select'),pick=el('select');
  question.placeholder='مثلاً چطور منابع پیشنهادی را ثبت کنم؟';question.setAttribute('aria-label','سؤال پایپ‌لاین');
  for(const [value,label] of [['answer','پایپ‌لاین پاسخ‌گویی'],['publication','پایپ‌لاین انتشار دانش']]){const option=el('option',label);option.value=value;mode.append(option)}
  mode.value=state.pipelineMode??'answer';mode.setAttribute('aria-label','نوع پایپ‌لاین');pick.setAttribute('aria-label','انتخاب اجرای پایپ‌لاین');
  const bar=el('div',undefined,'toolbar'),start=btn('اجرا و مشاهده مراحل',async()=>{start.disabled=true;try{const result=await api('pipeline/start','POST',{question:question.value});state.pipelineRun=result.id;state.pipelineMode='answer';mode.value='answer';await tick()}finally{start.disabled=false}},'');
  bar.append(mode,start,btn('نمای کامل',()=>{state.pipeZoom=null;lastRun=null;lastPublish=null;tick()},'ghost'),btn('بزرگ‌نمایی',()=>{state.pipeZoom=1.15;lastRun=null;lastPublish=null;tick()},'ghost'));controls.append(bar,question,el('p','سؤال در حالت Gemini مصرف توکن دارد. نمایش وضعیت از رویداد واقعی سرویس است؛ زمان انتظار مصنوعی اضافه نشده. این بخش ناظر پایپ‌لاین فعلی است و ویرایشگر دلخواه workflow نیست.','muted'),pick);
  const canvas=el('div',undefined,'pipeline-canvas'),grid=el('div',undefined,'grid2'),details=box('جزئیات مرحله'),result=box('نتیجه اجرا');details.id='pipeline-detail';result.id='pipeline-result';grid.append(details,result);c.append(controls,canvas,grid);
  const publication=box('رویدادهای انتشار');publication.classList.add('full');c.append(publication);let busy=false,lastRun=null,lastRuns=null,lastPublish=null;
  async function tick(){
    if(state.tab!=='pipeline'||busy)return;busy=true;
    try{
      question.classList.toggle('hidden',mode.value==='publication');start.classList.toggle('hidden',mode.value==='publication');pick.classList.toggle('hidden',mode.value==='publication');
      if(mode.value==='answer'){
        publication.classList.add('hidden');
        const runs=await api('pipeline/runs');if(state.tab!=='pipeline')return;
        const selected=state.pipelineRun??runs[0]?.id;
        const listSignature=JSON.stringify(runs);if(listSignature!==lastRuns){pick.replaceChildren();for(const run of runs){const option=el('option',run.question+' · '+statusLabel(run.status));option.value=run.id;pick.append(option)}lastRuns=listSignature}
        if(selected)pick.value=selected;
        if(!selected){result.replaceChildren(el('h2','هنوز پاسخی اجرا نشده است'));drawPipeline(canvas,[['policy','کنترل دامنه'],['topic','انتخاب منابع'],['retrieval','بازیابی Brain'],['selection','شواهد مجاز'],['generation','Gemini'],['validation','کنترل استناد'],['answer','پاسخ']].map(([id,label])=>({id,label,status:'pending'})));return}
        const run=await api('pipeline/runs/'+selected);if(state.tab!=='pipeline')return;
        const runSignature=JSON.stringify(run);if(runSignature===lastRun)return;lastRun=runSignature;
        drawPipeline(canvas,run.nodes);result.replaceChildren(el('h2',run.question),badge(statusLabel(run.status),run.status==='passed'?'green':'warn'),el('p','نسخه دانش: '+run.revision,'mono'),el('p','نسخه تنظیمات: '+run.settings_revision,'mono'));
        if(run.response)showData(result,'پاسخ واقعی و استنادها',run.response);
        showData(result,'رویدادهای همین اجرا',run.events);
        publication.classList.add('hidden');
      }else{
        publication.classList.remove('hidden');const data=await api('pipeline/publish');if(state.tab!=='pipeline')return;
        const publicationSignature=JSON.stringify(data);if(publicationSignature===lastPublish)return;lastPublish=publicationSignature;
        const phases=[['draft','خواندن نسخه کاری'],['materialize','آماده‌سازی ورودی'],['worker','Worker و Brain'],['publish','انتشار نسخه']];
        const nodes=phases.map(([id,label])=>{const event=data.events.filter(e=>e.stage===id).at(-1);return {id,label,status:event?.status??'pending',details:event??{}}});
        const failure=data.events.find(e=>e.status==='failed');if(failure){const active=nodes.find(n=>n.status==='running');if(active){active.status='failed';active.details=failure}}
        drawPipeline(canvas,nodes);result.replaceChildren(el('h2','انتشار دانش'),badge(data.running?'در حال اجرا':failure?'خطای انتشار':data.events.length?'پایان عملیات':'هنوز اجرا نشده'),el('p','نسخه فعال: '+data.revision,'mono'));
        publication.replaceChildren(el('h2','رویدادهای واقعی انتشار'),el('pre',JSON.stringify(data.events,null,2)));
      }
    }catch(e){if(state.tab==='pipeline'){result.replaceChildren(el('p','دریافت وضعیت ناموفق بود: '+e.message,'notice'))}}
    finally{busy=false;}
  }
  mode.onchange=()=>{state.pipelineMode=mode.value;lastRun=null;lastPublish=null;tick()};pick.onchange=()=>{state.pipelineRun=pick.value;lastRun=null;tick()};
  clearInterval(state.pipelineTimer);state.pipelineTimer=setInterval(tick,900);await tick();
};
