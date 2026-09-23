function linkedAnswer(text){return esc(text).replace(/\[gid:([0-9]+)\]/g,'<a href="#" onclick="showAssistantGid(\'$1\');return false">[gid:$1]</a>')}
function showAssistantGid(gid){showTab('graph');selectNode(String(gid))}
async function initAssistant(){
  var health=await get('/api/health'),status=document.getElementById('assistant-status');
  if(!health.llm_available){status.textContent='Assistant disabled: configure OPENAI_API_KEY or NVIDIA_API_KEY. Deterministic analysis remains available.'}
  document.querySelectorAll('.assistant-examples button').forEach(function(button){button.onclick=function(){document.getElementById('assistant-question').value=button.textContent}});
  document.getElementById('assistant-send').onclick=async function(){
    var question=document.getElementById('assistant-question').value.trim();if(!question)return;
    this.disabled=true;status.textContent='Thinking…';
    try{var result=await fetch('/api/assistant',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:question,history:[]})});var data=await result.json();if(!result.ok)throw Error(data.detail||result.statusText);document.getElementById('assistant-answer').innerHTML=linkedAnswer(data.answer||'');document.getElementById('assistant-tools').textContent=JSON.stringify(data.tool_calls||[],null,2);status.textContent='Answer grounded in graph tools.'}
    catch(e){status.textContent=e.message}finally{this.disabled=false}
  };
}
setTimeout(initAssistant,500);
