import cytoscape from 'cytoscape';
import { api } from './api.js';
import { state } from './state.js';
import { gid, money, number } from './format.js';

let cy, graph, selected = null, draggedAt = 0, positions = {}, positionKey = '';
const roleMeta = {
  consolidator: ['Сборщик', '#36a4d8'], coordinator: ['Кандидат в координаторы', '#a979e8'], distributor: ['Распределитель', '#ed8b4a'], transit: ['Транзит', '#36b88b'], terminal: ['Конечный получатель', '#e76f9a'], frontier: ['Обрыв обхода, 4-е колено', '#e6bd4f'], peripheral: ['Периферия', '#8795a1']
};
const filters = { priority: 0, amount: 0, nodes: 2248 };
let shownRoles = new Set(Object.keys(roleMeta));
const nodeId = n => gid(n.gid ?? n.id); // gid is deliberately never numeric
const amount = e => Number(e.sum_kzt ?? 0);
const score = n => Number(n.priority_score ?? n.priority ?? 0);
const short = id => `…${gid(id).slice(-6)}`;
const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

function parseAmount(value) {
  const t = String(value).trim().toLowerCase().replace(/\s/g, '').replace(',', '.');
  const m = t.match(/^([\d.]+)(к|k|млн|m)?$/); if (!m || Number.isNaN(Number(m[1]))) return null;
  return Number(m[1]) * ({ к: 1e3, k: 1e3, млн: 1e6, m: 1e6 }[m[2]] || 1);
}
function amountText(v) { return money(v); }
function storageLoad(key) { try { return JSON.parse(localStorage.getItem(key) || '{}'); } catch { return {}; } }
function storageSave() { try { localStorage.setItem(positionKey, JSON.stringify(positions)); } catch {} }
function original(id) { const n = graph.nodes.find(x => nodeId(x) === id); return { x: n.x || 0, y: n.y || 0 }; }

function panel() {
  const roles = Object.entries(roleMeta).map(([role, [label, color]]) => `<button data-role="${role}" class="legend-role active"><i style="--role:${color}"></i><span>${label}</span><b id="role-${role}">0</b></button>`).join('');
  return `<aside class="investigator-left"><header><b>Рабочий срез</b><button id="reset-filters" class="link-button">Сбросить</button></header><div class="filter-fields">
    <label>Мин. приоритет <input id="priority-text" inputmode="decimal" value="0"><input id="priority-range" type="range" min="0" max="1" step=".01" value="0"></label>
    <label>Мин. сумма связи <input id="amount-text" inputmode="decimal" value="0 KZT"><input id="amount-range" type="range" min="0" max="1000" step="1" value="0"></label>
    <label>Активных вершин <input id="nodes-text" inputmode="numeric" value="2248"><input id="nodes-range" type="range" min="20" max="2248" step="10" value="2248"></label>
  </div><details class="legend" open><summary>Легенда</summary>${roles}<p><i class="seed-key"></i>Seed — золотая обводка</p><p><i class="edge-in"></i>входящие · <i class="edge-out"></i>исходящие</p></details><p class="graph-hint">Фон — перемещение · узел — перетаскивание · колесо — масштаб · <kbd>/</kbd> — поиск</p></aside>`;
}

export async function graphView(root, openCard) {
  root.innerHTML = `<section class="investigator"><div id="left-slot">${panel()}</div><div class="graph-main"><div id="cy" class="cy" aria-label="Граф связей"></div><div id="tip" class="node-tip" popover></div><div class="graph-actions"><button id="zoom-in">+</button><button id="zoom-out">−</button><button id="fit">Вписать всё</button><button id="to-selected">К выбранному</button><button id="reset-layout">Сбросить раскладку</button></div></div></section>`;
  const [g, summary] = await Promise.all([api.get('/graph'), api.get('/summary').catch(() => ({}))]);
  graph = { nodes: g.nodes || [], edges: g.edges || [] };
  filters.nodes = Math.min(filters.nodes, graph.nodes.length);
  positionKey = `graph-positions:${graph.nodes.length}-${graph.edges.length}-${summary.elapsed_seconds || summary.run_at || ''}`;
  positions = storageLoad(positionKey);
  const maxSum = Math.max(1, ...graph.edges.map(amount));
  const elements = [
    ...graph.nodes.map(n => ({ group: 'nodes', data: { ...n, id: nodeId(n), gid: nodeId(n), label: short(nodeId(n)), priority: score(n) }, position: positions[nodeId(n)] || { x: n.x, y: n.y }, classes: `${n.role || 'peripheral'}${n.is_seed ? ' seed' : ''}` })),
    ...graph.edges.map((e, i) => ({ group: 'edges', data: { ...e, id: gid(e.id || `edge-${i}`), source: gid(e.source), target: gid(e.target), sum_kzt: amount(e) } }))
  ];
  const opts = { container: root.querySelector('#cy'), elements, layout: { name: 'preset' }, minZoom: .05, maxZoom: 4, userPanningEnabled: true, autoungrabify: false, boxSelectionEnabled: false, textureOnViewport: true, hideEdgesOnViewport: true, motionBlur: false, pixelRatio: 1, renderer: { name: 'canvas', webgl: true }, style: [
    { selector: 'node', style: { shape: 'ellipse', 'background-color': n => roleMeta[n.data('role')]?.[1] || '#8795a1', width: n => 12 + Math.min(24, Math.sqrt(n.data('priority') || 0) * 24), height: n => 12 + Math.min(24, Math.sqrt(n.data('priority') || 0) * 24), 'border-width': 2, 'border-color': '#16212b', label: 'data(label)', 'font-family': 'ui-monospace, monospace', 'font-size': 9, color: '#e5edf4', 'text-valign': 'bottom', 'text-margin-y': 4, 'text-opacity': 0 } },
    { selector: 'node.seed', style: { 'border-color': '#e6bd4f', 'border-width': 4 } }, { selector: 'node.frontier', style: { 'border-style': 'dashed' } },
    { selector: 'node.label, node.selected, node.neighbor', style: { 'text-opacity': 1 } }, { selector: 'node.dim, edge.dim', style: { opacity: .15 } },
    { selector: 'node.selected', style: { 'border-color': '#70d7ff', 'border-width': 5, 'underlay-opacity': 0 } },
    { selector: 'node.hidden, edge.hidden', style: { display: 'none' } },
    { selector: 'edge', style: { width: e => Math.max(1, Math.min(6, Math.log10(e.data('sum_kzt') + 1))), 'curve-style': 'straight', 'line-color': '#627689', 'target-arrow-color': '#627689', 'target-arrow-shape': 'triangle', 'arrow-scale': .7, opacity: .7 } },
    { selector: 'edge.incoming', style: { 'line-color': '#f0b35c', 'target-arrow-color': '#f0b35c', opacity: 1 } }, { selector: 'edge.outgoing', style: { 'line-color': '#54c7e8', 'target-arrow-color': '#54c7e8', opacity: 1 } }
  ] };
  try { cy = cytoscape(opts); } catch { delete opts.renderer.webgl; cy = cytoscape(opts); }
  bind(root, openCard, maxSum); apply(root, maxSum, false); cy.fit(cy.elements(':visible'), 50);
  window.focusNode = value => focus(gid(value), root, openCard, maxSum);
  if (state.node) focus(state.node, root, openCard, maxSum);
}
function bind(root, openCard, maxSum) {
  const update = debounce(() => apply(root, maxSum, true), 150);
  const pair = (text, range, key, parse, format) => { const t = root.querySelector(text), r = root.querySelector(range); r.oninput = () => { filters[key] = key === 'amount' ? maxSum * (r.value / 1000) ** 4 : Number(r.value); t.value = format(filters[key]); update(); }; const commit = () => { const v = parse(t.value); if (v === null || v < 0) { t.classList.add('invalid'); t.value = format(filters[key]); return; } t.classList.remove('invalid'); filters[key] = Math.min(key === 'nodes' ? graph.nodes.length : key === 'priority' ? 1 : maxSum, v); r.value = key === 'amount' ? Math.round(1000 * (filters[key] / maxSum) ** .25) : filters[key]; t.value = format(filters[key]); update(); }; t.onblur = commit; t.onkeydown = e => e.key === 'Enter' && commit(); };
  pair('#priority-text', '#priority-range', 'priority', v => Number(String(v).replace(',','.')), v => v.toFixed(2)); pair('#amount-text', '#amount-range', 'amount', parseAmount, amountText); pair('#nodes-text', '#nodes-range', 'nodes', v => /^\d+$/.test(v) ? Number(v) : null, number);
  root.querySelector('#reset-filters').onclick = () => { filters.priority=0; filters.amount=0; filters.nodes=graph.nodes.length; state.cluster=null; root.querySelector('#priority-text').value='0.00'; root.querySelector('#priority-range').value=0; root.querySelector('#amount-text').value='0 KZT';root.querySelector('#amount-range').value=0;root.querySelector('#nodes-text').value=filters.nodes;root.querySelector('#nodes-range').value=filters.nodes;shownRoles=new Set(Object.keys(roleMeta));root.querySelectorAll('.legend-role').forEach(x=>x.classList.add('active'));apply(root,maxSum,true); };
  root.querySelectorAll('.legend-role').forEach(b => b.onclick = () => { const r=b.dataset.role;shownRoles.has(r)?shownRoles.delete(r):shownRoles.add(r);b.classList.toggle('active',shownRoles.has(r));apply(root,maxSum,true); });
  root.querySelector('#zoom-in').onclick=()=>cy.zoom({level:Math.min(4,cy.zoom()*1.25),renderedPosition:{x:cy.width()/2,y:cy.height()/2}}); root.querySelector('#zoom-out').onclick=()=>cy.zoom({level:Math.max(.05,cy.zoom()/1.25),renderedPosition:{x:cy.width()/2,y:cy.height()/2}});root.querySelector('#fit').onclick=()=>cy.fit(cy.elements(':visible'),50);root.querySelector('#to-selected').onclick=()=>selected&&cy.animate({center:{eles:cy.$id(selected)},zoom:Math.max(1.2,cy.zoom())},{duration:300});root.querySelector('#reset-layout').onclick=()=>{positions={};try{localStorage.removeItem(positionKey)}catch{};cy.nodes().forEach(n=>n.position(original(n.id())));};
  cy.on('tap','node',e=>{ if (performance.now()-draggedAt>180) focus(e.target.id(),root,openCard,maxSum); });cy.on('dragfree','node',e=>{draggedAt=performance.now();positions[e.target.id()]=e.target.position();storageSave();});
  let timer;cy.on('zoom',()=>{clearTimeout(timer);timer=setTimeout(()=>cy.nodes().toggleClass('label',cy.zoom()>=1.2),100)}); cy.on('mouseover','node',e=>showTip(root,e.target));cy.on('mouseout','node',()=>root.querySelector('#tip').hidePopover());
  document.onkeydown=e=>{if(e.key==='Escape'){selected=null;apply(root,maxSum,false);}};
}
function apply(root,maxSum,fit){const allowed=graph.nodes.filter(n=>shownRoles.has(n.role)&&score(n)>=filters.priority&&(!state.cluster||String(n.cluster_id??n.cluster)===String(state.cluster))).sort((a,b)=>score(b)-score(a)||nodeId(a).localeCompare(nodeId(b),'ru',{numeric:true})).slice(0,filters.nodes);const ids=new Set(allowed.map(nodeId));const edgeIds=new Set(graph.edges.filter(e=>ids.has(gid(e.source))&&ids.has(gid(e.target))&&amount(e)>=filters.amount).map((e,i)=>gid(e.id||`edge-${graph.edges.indexOf(e)}`)));cy.batch(()=>{cy.nodes().forEach(n=>n.toggleClass('hidden',!ids.has(n.id())).removeClass('dim neighbor selected'));cy.edges().forEach(e=>e.toggleClass('hidden',!edgeIds.has(e.id())).removeClass('dim incoming outgoing'));if(selected){const n=cy.$id(selected), hood=n.closedNeighborhood();cy.elements(':visible').not(hood).addClass('dim');n.addClass('selected');n.neighborhood('node').addClass('neighbor');n.incomers('edge').addClass('incoming');n.outgoers('edge').addClass('outgoing');}});Object.keys(roleMeta).forEach(r=>root.querySelector(`#role-${r}`).textContent=graph.nodes.filter(n=>n.role===r&&(!state.cluster||String(n.cluster_id??n.cluster)===String(state.cluster))).length);if(fit)cy.fit(cy.elements(':visible'),50)}
function focus(id,root,openCard,maxSum){if(!cy.$id(id).length)return;selected=id;state.node=id;apply(root,maxSum,false);cy.animate({center:{eles:cy.$id(id)},zoom:Math.max(1.2,cy.zoom())},{duration:300});openCard(id)}
function showTip(root,n){const tip=root.querySelector('#tip');tip.textContent=`${n.data('gid')} · ${roleMeta[n.data('role')]?.[0]||'—'} · приоритет ${score(n.data()).toFixed(2)} · вход ${money(n.data('in_kzt'))} · выход ${money(n.data('out_kzt'))}`;tip.showPopover();}
