var resilienceCharts={};
function renderSummary(summary){
  var counts=summary.role_counts||summary.roles||{};
  var roles=Object.keys(counts).map(function(k){return k+': '+counts[k]}).join(' · ');
  document.getElementById('summary').textContent='Nodes: '+(summary.n_nodes||'—')+' · Seeds: '+(summary.n_seed||'—')+' · '+roles+' · Runtime: '+(summary.elapsed_seconds==null?'—':Number(summary.elapsed_seconds).toFixed(2)+'s');
}
function lineChart(id,title,series,labels){
  if(resilienceCharts[id])resilienceCharts[id].destroy();
  var colors={by_priority:'#63d4c5',by_degree:'#f59e0b',random:'#9b8cff'};
  resilienceCharts[id]=new Chart(document.getElementById(id),{type:'line',data:{labels:labels,datasets:Object.keys(series).map(function(k){return{label:k.replace('by_',''),data:series[k],borderColor:colors[k]||'#718096',backgroundColor:'transparent',tension:.2}})},options:{responsive:true,maintainAspectRatio:false,plugins:{title:{display:true,text:title,color:'#e8eef5'},legend:{labels:{color:'#8fa1b3'}}},scales:{x:{title:{display:true,text:'Removed nodes',color:'#8fa1b3'},ticks:{color:'#8fa1b3'}},y:{ticks:{color:'#8fa1b3'},grid:{color:'#2b3948'}}}}});
}
async function loadResilience(){
  var data=await get('/api/resilience');
  var empty=!data||!Array.isArray(data.n_removed)||!data.n_removed.length;
  document.getElementById('resilience-status').textContent=empty?'Resilience data will appear after the pipeline extension.':'Removal curves computed from the latest pipeline output.';
  if(empty)return;
  lineChart('lwcc-chart','Largest weakly connected component',data.by_priority||{},data.n_removed);
  lineChart('seed-chart','Seed-reachable nodes',data.by_priority||{},data.n_removed);
  var p=data.by_priority&&data.by_priority.lwcc_size?data.by_priority.lwcc_size[0]-data.by_priority.lwcc_size[Math.min(4,data.by_priority.lwcc_size.length-1)]:0;
  document.getElementById('drop-summary').textContent='Removal top-20: −'+(Number(p)||0).toFixed(1)+'% connectivity change.';
}
async function initStage2C(){
  try{renderSummary(await get('/api/summary'));await loadResilience()}catch(e){document.getElementById('resilience-status').textContent=e.message}
  document.getElementById('rerun-pipeline').onclick=async function(){
    this.disabled=true;document.getElementById('resilience-status').textContent='Recalculating…';
    try{await fetch('/api/pipeline/run',{method:'POST'});location.reload()}catch(e){document.getElementById('resilience-status').textContent=e.message;this.disabled=false}
  };
}
setTimeout(initStage2C,500);
