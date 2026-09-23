const sliceKey = 'trace-working-slice-collapsed-v2';
const panelKey = 'trace-filters-collapsed-v2';

const read = (key, fallback = false) => { try { return localStorage.getItem(key) === 'true'; } catch { return fallback; } };
const write = (key, value) => { try { localStorage.setItem(key, String(value)); } catch {} };

function resizeGraph() {
  window.dispatchEvent(new Event('resize'));
}

function setPanel(panel, collapsed) {
  const graph = panel.closest('.investigator');
  if (!graph) return;
  graph.classList.toggle('filters-collapsed', collapsed);
  panel.querySelector('.panel-collapse')?.setAttribute('aria-expanded', String(!collapsed));
  document.querySelector('#toggle-filters')?.setAttribute('aria-pressed', String(collapsed));
  write(panelKey, collapsed);
  setTimeout(resizeGraph, 220);
}

function setSlice(panel, collapsed) {
  const body = panel.querySelector('.slice-body');
  const button = panel.querySelector('.slice-toggle');
  if (!body || !button) return;
  body.classList.toggle('is-collapsed', collapsed);
  button.setAttribute('aria-expanded', String(!collapsed));
  button.querySelector('.slice-chevron').textContent = collapsed ? '▶' : '▼';
  write(sliceKey, collapsed);
}

function setup(panel) {
  if (panel.dataset.sliceReady) return;
  panel.dataset.sliceReady = 'true';
  const header = panel.querySelector(':scope > header');
  const fields = panel.querySelector(':scope > .filter-fields');
  if (!header || !fields) return;
  const title = header.querySelector('b');
  const reset = header.querySelector('#reset-filters');
  const body = document.createElement('div');
  body.className = 'slice-body'; body.id = 'working-slice-body';
  fields.replaceWith(body); body.append(fields);
  const toggle = document.createElement('button');
  toggle.type = 'button'; toggle.className = 'slice-toggle'; toggle.setAttribute('aria-controls', body.id);
  toggle.innerHTML = '<span class="slice-chevron" aria-hidden="true">▼</span><span>Рабочий срез</span>';
  title.replaceWith(toggle);
  const collapse = document.createElement('button');
  collapse.type = 'button'; collapse.className = 'panel-collapse'; collapse.setAttribute('aria-label', 'Свернуть боковую панель'); collapse.innerHTML = '‹';
  header.insertBefore(collapse, reset);
  const reopen = document.createElement('button');
  reopen.type = 'button'; reopen.className = 'panel-reopen'; reopen.setAttribute('aria-label', 'Раскрыть боковую панель'); reopen.innerHTML = '›';
  panel.closest('.investigator').append(reopen);
  toggle.addEventListener('click', () => setSlice(panel, !body.classList.contains('is-collapsed')));
  toggle.addEventListener('keydown', event => { if (event.key === ' ' || event.key === 'Enter') { event.preventDefault(); toggle.click(); } });
  reset.addEventListener('click', event => event.stopPropagation());
  collapse.addEventListener('click', () => setPanel(panel, !panel.closest('.investigator').classList.contains('filters-collapsed')));
  reopen.addEventListener('click', () => setPanel(panel, false));
  setSlice(panel, read(sliceKey));
  setPanel(panel, read(panelKey));
}

document.querySelector('#toggle-filters')?.addEventListener('click', () => {
  const panel = document.querySelector('.investigator-left');
  if (panel) setPanel(panel, !panel.closest('.investigator').classList.contains('filters-collapsed'));
});
new MutationObserver(() => document.querySelectorAll('.investigator-left').forEach(setup)).observe(document.querySelector('#view'), { childList: true });
