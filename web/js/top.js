import { api } from './api.js';
import { gid, esc } from './format.js';

const percent = value => {
  const number = Number(value || 0);
  return number <= 1 ? number * 100 : number;
};

export async function topView(root) {
  root.innerHTML = '<div class="table-tools"><input id="top-filter" placeholder="Фильтр gid / роль"><button id="csv" class="button">CSV</button></div><div class="data-table"><div class="thead"><span>#</span><span>gid</span><span>Роль</span><span>Приоритет</span><span>Почему</span></div><div id="top-body"></div></div>';
  const data = await api.get('/top');
  let rows = data.items || data || [];
  const render = () => {
    root.querySelector('#top-body').innerHTML = rows.map((row, index) => {
      const priority = percent(row.priority_score);
      return `<button data-gid="${gid(row.gid)}"><span>${index + 1}</span><code>${gid(row.gid)}</code><span class="badge ${row.role}">${esc(row.role || '—')}</span><span class="priority"><i style="width:${priority}%"></i>${priority.toFixed(1)}%</span><span>${esc(row.why || row.evidence || 'Связи и оборот')}</span></button>`;
    }).join('');
  };
  render();
  root.querySelector('#top-filter').oninput = event => {
    const query = event.target.value.toLowerCase();
    rows = (data.items || data || []).filter(row => gid(row.gid).includes(query) || (row.role || '').toLowerCase().includes(query));
    render();
  };
  root.addEventListener('click', event => {
    const button = event.target.closest('[data-gid]');
    if (button) location.href = `?tab=graph&node=${encodeURIComponent(button.dataset.gid)}`;
  });
  root.querySelector('#csv').onclick = () => exportCsv(rows, 'top.csv');
}

export function exportCsv(rows, name) {
  const fields = ['gid', 'role', 'priority_score', 'evidence'];
  const csv = '\ufeff' + fields.join(';') + '\n' + rows.map(row => fields.map(field => `"${String(row[field] ?? '').replaceAll('"', '""')}"`).join(';')).join('\n');
  const anchor = document.createElement('a');
  anchor.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
  anchor.download = name;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(anchor.href), 1000);
}
