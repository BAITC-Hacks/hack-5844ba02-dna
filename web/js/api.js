import { mockApi } from './mock.js';
const cache=new Map(), base='/api'; let demo=new URLSearchParams(location.search).get('mock')==='1';
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
export const invalidate=()=>cache.clear(); export const isDemo=()=>demo;
async function request(path,{method='GET',body,signal}={}){const key=method+path;if(method==='GET'&&cache.has(key))return structuredClone(cache.get(key)); if(demo)return mockApi(path,{method,body}); let err; for(let i=0;i<(method==='GET'?2:1);i++){const ctrl=new AbortController(),t=setTimeout(()=>ctrl.abort(),7000); try { const r=await fetch(base+path,{method,body:body&&JSON.stringify(body),headers:{'content-type':'application/json'},signal:signal||ctrl.signal}); clearTimeout(t); if(!r.ok)throw Error(`API ${r.status}`); const d=await r.json();if(method==='GET')cache.set(key,d);return structuredClone(d);}catch(e){err=e;clearTimeout(t);if(signal||i)break;await sleep(250);}} demo=true; document.documentElement.dataset.demo='1'; return mockApi(path,{method,body});}
export const api={get:(p,o)=>request(p,o),post:(p,b)=>request(p,{method:'POST',body:b}),health:()=>request('/health')};
