import { api, isDemo, invalidate } from './js/api.js';
import { state } from './js/state.js';
import { gid, number, esc } from './js/format.js';
import { graphView } from './js/graph.js';
import { openCard } from './js/card.js';
import { topView, exportCsv } from './js/top.js';
import { clustersView } from './js/clusters.js';
import { resilienceView } from './js/resilience.js';
import { assistantView } from './js/assistant.js';

const $ = selector => document.querySelector(selector);
const view = $('#view');
const params = new URLSearchParams(location.search);
state.tab = params.get('tab') || 'graph';
state.node = params.get('node');
state.cluster = params.get('cluster');
state.mode = params.get('mode') || 'all';

const tabs = {
  graph: () => graphView(view, openCard),
  top: () => topView(view),
  clusters: () => clustersView(view),
  resilience: () => resilienceView(view),
  assistant: () => assistantView(view),
};

function transition(fn) {
  return document.startViewTransition ? document.startViewTransition(fn) : fn();
}

function emptyState(message) {
  view.innerHTML = `<div class="empty"><div><h2>Данные не загружены</h2><p>${esc(message)}</p><code>make pipeline</code></div></div>`;
}

async function show(tab, push = true) {
  state.tab = tabs[tab] ? tab : 'graph';
  if (push) {
    const url = new URL(location);
    url.searchParams.set('tab', state.tab);
    if (state.node) url.searchParams.set('node', state.node); else url.searchParams.delete('node');
    if (state.cluster) url.searchParams.set('cluster', state.cluster); else url.searchParams.delete('cluster');
    history.pushState({}, '', url);
  }
  document.querySelectorAll('[role=tab]').forEach(button => {
    const selected = button.dataset.tab === state.tab;
    button.ariaSelected = selected;
    button.tabIndex = selected ? 0 : -1;
    button.classList.toggle('active', selected);
  });
  if (!state.outLoaded && !isDemo()) {
    emptyState('Сначала запустите пайплайн: make pipeline');
    return;
  }
  view.innerHTML = '<div class="skeleton view-skeleton"></div>';
  try {
    await tabs[state.tab]();
  } catch (error) {
    view.innerHTML = `<div class="empty">Не удалось загрузить раздел: ${esc(error.message || error)}</div>`;
  }
}

window.addEventListener('popstate', () => {
  const query = new URLSearchParams(location.search);
  state.node = query.get('node');
  state.cluster = query.get('cluster');
  show(query.get('tab') || 'graph', false);
});
document.querySelectorAll('[role=tab]').forEach(button => { button.onclick = () => show(button.dataset.tab); });

function toast(message) {
  const element = $('#toast');
  element.textContent = message;
  element.classList.add('show');
  setTimeout(() => element.classList.remove('show'), 3500);
}

async function init() {
  try {
    const health = await api.health();
    state.outLoaded = isDemo() || health.out_loaded === true;
    state.llmAvailable = isDemo() || health.llm_available === true;
    $('#api-status').textContent = isDemo() ? '● ОФЛАЙН · ДЕМО-ДАННЫЕ' : '● API ГОТОВ';
    if (!state.outLoaded) {
      $('#summary-chips').innerHTML = '<span>Нет результатов pipeline</span>';
      await show(state.tab, false);
      return;
    }
    const summary = await api.get('/summary');
    const roles = summary.roles || summary.role_counts || {};
    $('#summary-chips').innerHTML = `<span>${number(summary.nodes ?? summary.n_nodes)} узлов</span><span>${number(summary.seeds ?? summary.n_seed ?? 0)} seed</span>${Object.entries(roles).slice(0, 3).map(([role, value]) => `<span class="role-chip ${role}">${role} ${number(value)}</span>`).join('')}`;
    await show(state.tab, false);
  } catch (error) {
    state.outLoaded = false;
    state.llmAvailable = false;
    $('#api-status').textContent = '● API НЕДОСТУПЕН';
    emptyState(error.message || 'Не удалось подключиться к API');
  }
}

let timer;
$('#run').onclick = async () => {
  const button = $('#run');
  const started = performance.now();
  button.disabled = true;
  button.textContent = 'Пересчёт…';
  timer = setInterval(() => { button.textContent = `${((performance.now() - started) / 1000).toFixed(1)} c`; }, 100);
  try {
    const result = await api.post('/pipeline/run', {});
    invalidate();
    const seconds = result.elapsed_sec ?? (result.duration_ms || performance.now() - started) / 1000;
    toast(`Пересчёт завершён за ${Number(seconds).toFixed(1)} с`);
    await init();
  } catch {
    toast('Не удалось запустить пересчёт');
  } finally {
    clearInterval(timer);
    button.disabled = false;
    button.textContent = 'Пересчитать';
  }
};

let abort;
let debounce;
const search = $('#search');
const suggestions = $('#suggestions');
search.oninput = () => {
  clearTimeout(debounce);
  const query = search.value.trim();
  if (!query) { suggestions.innerHTML = ''; return; }
  debounce = setTimeout(async () => {
    abort?.abort();
    abort = new AbortController();
    try {
      const rows = await api.get(`/search?q=${encodeURIComponent(query)}`, { signal: abort.signal });
      suggestions.innerHTML = (rows.items || rows || []).map(row => `<button role="option" data-gid="${gid(row.gid)}"><code>${gid(row.gid).replace(query, `<mark>${query}</mark>`)}</code><span class="badge ${row.role}">${row.role || ''}</span><b>${row.priority_score ?? ''}</b></button>`).join('');
    } catch { suggestions.innerHTML = ''; }
  }, 120);
};
search.onkeydown = event => {
  const buttons = [...suggestions.querySelectorAll('button')];
  let index = buttons.findIndex(button => button.classList.contains('selected'));
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault();
    index = (index + (event.key === 'ArrowDown' ? 1 : -1) + buttons.length) % buttons.length;
    buttons.forEach(button => button.classList.remove('selected'));
    buttons[index]?.classList.add('selected');
  }
  if (event.key === 'Enter') {
    const target = buttons[index] || buttons[0];
    if (target) {
      state.node = target.dataset.gid;
      state.cluster = null;
      show('graph');
      search.value = '';
      suggestions.innerHTML = '';
    }
  }
};
suggestions.onclick = event => {
  const button = event.target.closest('[data-gid]');
  if (button) {
    state.node = button.dataset.gid;
    state.cluster = null;
    show('graph');
    suggestions.innerHTML = '';
  }
};

$('#theme').onclick = () => {
  const modes = ['dark', 'light', 'system'];
  state.theme = modes[(modes.indexOf(state.theme) + 1) % modes.length];
  document.documentElement.dataset.theme = state.theme;
  document.documentElement.style.colorScheme = state.theme === 'system' ? 'light dark' : state.theme;
  try { localStorage.setItem('trace-theme', state.theme); } catch {}
  toast(`Тема: ${state.theme === 'dark' ? 'тёмная' : state.theme === 'light' ? 'светлая' : 'система'}`);
  if (state.tab === 'resilience') show('resilience', false);
};
document.documentElement.dataset.theme = state.theme;

const palette = $('#palette');
const paletteInput = $('#palette-input');
const paletteResults = $('#palette-results');
function openPalette() {
  palette.showModal();
  paletteInput.value = '';
  paletteResults.innerHTML = '<button data-tab="graph">Перейти: Граф</button><button data-tab="top">Перейти: Топ</button><button data-action="theme">Сменить тему</button><button data-action="run">Пересчитать</button>';
}
document.addEventListener('keydown', event => {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); openPalette(); }
  if (event.key === '/' && document.activeElement !== search && !['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName)) { event.preventDefault(); search.focus(); }
  if (event.key === 'Escape') $('#card').classList.remove('open');
  if (event.key.toLowerCase() === 'f' && state.tab === 'graph') document.querySelector('#fit')?.click();
  if (/^[1-5]$/.test(event.key)) show(['graph', 'top', 'clusters', 'resilience', 'assistant'][Number(event.key) - 1]);
});
paletteResults.onclick = event => {
  const button = event.target.closest('button');
  if (!button) return;
  palette.close();
  if (button.dataset.tab) show(button.dataset.tab);
  if (button.dataset.action === 'theme') $('#theme').click();
  if (button.dataset.action === 'run') $('#run').click();
};

window.addEventListener('review', () => { $('#review-count').textContent = state.review.length; });
$('#review-btn').onclick = () => {
  const dialog = $('#review');
  $('#review-list').innerHTML = state.review.length ? state.review.map(row => `<p><code>${row.gid}</code> ${row.role} <button data-gid="${row.gid}">Удалить</button></p>`).join('') : '<div class="empty">Перечень пока пуст.</div>';
  dialog.showModal();
  $('#review-list').onclick = event => {
    const button = event.target.closest('[data-gid]');
    if (button) {
      state.review = state.review.filter(row => row.gid !== button.dataset.gid);
      event.target.closest('p').remove();
      window.dispatchEvent(new Event('review'));
    }
  };
};
$('#export-review').onclick = () => exportCsv(state.review, 'trace-review.csv');
$('#help').onclick = () => toast(' / поиск · ⌘K палитра · 1–5 вкладки · Esc снять фокус · F вписать');

init();
