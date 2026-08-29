const $=(s)=>document.querySelector(s);const $$=(s)=>[...document.querySelectorAll(s)];let current=null;

function fmtStatus(value){return String(value||"—").replaceAll("_"," ")}

async function boot(){
  try{const h=await fetch('/api/health').then(r=>r.json());const p=$('#healthPill');p.textContent=h.ok?'runtime online':'runtime error';p.classList.add(h.ok?'good':'bad')}catch{$('#healthPill').textContent='runtime unavailable';$('#healthPill').classList.add('bad')}
  try{current=await fetch('/api/current').then(r=>r.json());renderSystem(current);$('#coreStatus').textContent=fmtStatus(current.status.detector_core);$('#validationStatus').textContent=fmtStatus(current.status.historical_validation);$('#top15Status').textContent=fmtStatus(current.status.top15_assembler)}catch(e){$('#validationStatus').textContent='snapshot error'}
}

$$('.nav-item').forEach(btn=>btn.addEventListener('click',()=>{const name=btn.dataset.view;$$('.nav-item').forEach(x=>x.classList.toggle('active',x===btn));$$('.view').forEach(v=>v.classList.toggle('active',v.id===`view-${name}`))}));

$('#searchForm').addEventListener('submit',async(e)=>{e.preventDefault();const direction=$('#direction').value.trim();if(!direction)return;const res=await fetch('/api/analyze',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({direction})});const body=await res.json();if(body.ok&&body.item){showCase(body.item);return}showNotComputed(body,direction)});

function showNotComputed(body,direction){$('#resultPanel').classList.add('hidden');const panel=$('#emptyPanel');panel.classList.remove('hidden');panel.innerHTML=`<span class="eyebrow">DYNAMIC ANALYSIS NOT WIRED YET</span><h2>«${escapeHtml(direction)}» пока не рассчитано</h2><p>${escapeHtml(body.message||'Для этого направления ещё нет опубликованного snapshot.')}</p><p>Сейчас доступны: ${(body.available||[]).map(x=>`<strong>${escapeHtml(x.id.toUpperCase())}</strong>`).join(' · ')}</p>`}

function showCase(item){$('#emptyPanel').classList.add('hidden');$('#resultPanel').classList.remove('hidden');$('#resultTitle').textContent=item.label;$('#diagnosticText').textContent=item.diagnostic?.message||'';$('#originDate').textContent=item.origin.date;$('#milestoneDate').textContent=item.milestone.date;$('#rawSignal').textContent=item.summary.first_raw_activity;$('#preOrigin').textContent=Number(item.summary.pre_origin_count).toLocaleString('ru-RU');$('#originTitle').textContent=item.origin.title;$('#originLink').href=item.origin.url;$('#milestoneTitle').textContent=item.milestone.title;$('#milestoneLink').href=item.milestone.url;drawChart(item.curve)}

function drawChart(curve){const canvas=$('#trendChart'),ctx=canvas.getContext('2d');const dpr=window.devicePixelRatio||1;const cssW=canvas.clientWidth||1000,cssH=330;canvas.width=cssW*dpr;canvas.height=cssH*dpr;ctx.scale(dpr,dpr);ctx.clearRect(0,0,cssW,cssH);const pad={l:54,r:18,t:18,b:34},w=cssW-pad.l-pad.r,h=cssH-pad.t-pad.b;const research=curve.map(x=>x.research),impl=curve.map(x=>x.implementation);const max=Math.max(...research,1);ctx.strokeStyle='#253041';ctx.fillStyle='#93a0b2';ctx.font='11px system-ui';for(let i=0;i<=4;i++){const y=pad.t+h*(i/4);ctx.beginPath();ctx.moveTo(pad.l,y);ctx.lineTo(cssW-pad.r,y);ctx.stroke();ctx.fillText(Math.round(max*(1-i/4)).toLocaleString('ru-RU'),4,y+4)}const line=(vals,color,scaleMax)=>{ctx.strokeStyle=color;ctx.lineWidth=2;ctx.beginPath();vals.forEach((v,i)=>{const x=pad.l+w*(i/Math.max(1,vals.length-1));const y=pad.t+h-(v/Math.max(1,scaleMax))*h;i?ctx.lineTo(x,y):ctx.moveTo(x,y)});ctx.stroke()};line(research,'#8fb4ff',max);const implMax=Math.max(...impl,1);line(impl,'#79d9a6',implMax);const ticks=[0,Math.floor((curve.length-1)/2),curve.length-1];ticks.forEach(i=>{const x=pad.l+w*(i/Math.max(1,curve.length-1));ctx.fillStyle='#93a0b2';ctx.fillText(curve[i].period,x-18,cssH-9)})}

function renderSystem(data){const rows={"Snapshot generated":data.generated_at,"Validation version":data.validation_version,"Detector core":data.status.detector_core,"TOP-15 assembler":data.status.top15_assembler,"Dynamic query API":data.status.dynamic_query_api,"Historical validation":data.status.historical_validation,"DeepSeek analyst":"CI batch layer — secret never exposed to browser"};$('#systemDetails').innerHTML=Object.entries(rows).map(([k,v])=>`<div class="system-row"><span>${escapeHtml(k)}</span><strong>${escapeHtml(fmtStatus(v))}</strong></div>`).join('')}
function escapeHtml(s){return String(s).replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]))}

boot();
