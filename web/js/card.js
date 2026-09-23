import { api } from './api.js';
import { money, pct, gid, esc } from './format.js';
import { state } from './state.js';

const percent = value => {
  const number = Number(value || 0);
  return number <= 1 ? number * 100 : number;
};

const table = (title, rows) => `<h3>${title}</h3><div class="mini-table">${(rows || []).map(row => `<button data-gid="${gid(row.gid)}"><code>${gid(row.gid)}</code><span>${row.role || '—'}</span><b title="${money(row.sum_kzt, true)}">${money(row.sum_kzt)}</b></button>`).join('')}</div>`;

export async function openCard(id) {
  const panel = document.querySelector('#card');
  panel.classList.add('open');
  panel.innerHTML = '<button id="close-card" class="close">×</button><div class="skeleton lines"></div>';
  try {
    const card = await api.get(`/node/${encodeURIComponent(gid(id))}/card`);
    const metrics = card.metrics || card.flows || card;
    const breakdown = Object.entries(card.score_breakdown || {}).sort((a, b) => Number(b[1]) - Number(a[1]));
    panel.innerHTML = `<button id="close-card" class="close">×</button><header><code>${gid(card.gid ?? id)}</code><button id="copy" class="icon-btn">□</button><span class="badge ${card.role || ''}">${card.role || 'unknown'}</span></header><div class="score-row"><div><strong>${Math.round(percent(card.role_score))}%</strong><small>role score</small></div><div><strong>${Math.round(percent(card.priority_score))}%</strong><small>priority</small></div><button class="cluster">Кластер ${gid(card.cluster_id ?? '—')}</button></div><section class="evidence">${esc(card.evidence || card.why || 'Доказательства пока не сформированы.')}</section><h3>Разложение приоритета</h3><div class="breakdown">${breakdown.map(([key, value]) => `<div><span>${esc(key)}</span><i><b style="width:${Math.min(100, percent(value))}%"></b></i><em>${Math.round(percent(value))}</em></div>`).join('')}</div><div class="metrics"><div>Вход <b title="${money(metrics.in_kzt, true)}">${money(metrics.in_kzt)}</b></div><div>Выход <b title="${money(metrics.out_kzt, true)}">${money(metrics.out_kzt)}</b></div><div>Контрагенты <b>${metrics.counterparties ?? '—'}</b></div><div>Pass ratio <b>${pct(metrics.pass_ratio)}</b></div><div>Seed flow <b>${money(metrics.seed_flow_kzt)}</b></div><div>p terminal <b>${metrics.p_terminal == null ? '—' : pct(metrics.p_terminal)}</b></div></div>${Number(metrics.pass_ratio || 0) > 1.2 ? '<p class="notice">Есть источники вне выборки</p>' : ''}${table('Кто платит', card.payers || card.top_counterparties?.incoming)}${table('Кому платит', card.payees || card.top_counterparties?.outgoing)}<h3>Следующие шаги</h3><ol>${(card.next_steps || []).map(step => `<li>${esc(step)}</li>`).join('')}</ol><footer><button id="add-review" class="button">Добавить в перечень</button>${card.llm_available ? '<button id="llm" class="button">Сформировать справку ИИ</button>' : ''}</footer><div id="llm-output"></div>`;

    panel.querySelector('#close-card').onclick = () => panel.classList.remove('open');
    panel.querySelector('#copy').onclick = async () => {
      try { await navigator.clipboard.writeText(gid(card.gid ?? id)); panel.querySelector('#copy').textContent = '✓'; } catch {}
    };
    panel.querySelectorAll('[data-gid]').forEach(button => { button.onclick = () => window.focusNode(button.dataset.gid); });
    panel.querySelector('#add-review').onclick = () => {
      const value = gid(card.gid ?? id);
      if (!state.review.some(row => row.gid === value)) state.review = [...state.review, { gid: value, role: card.role, priority_score: card.priority_score }];
      window.dispatchEvent(new Event('review'));
    };
    panel.querySelector('#llm')?.addEventListener('click', async () => {
      const output = panel.querySelector('#llm-output');
      output.innerHTML = '<div class="skeleton lines"></div>';
      const result = await api.post(`/node/${encodeURIComponent(gid(id))}/card/llm`, {});
      output.textContent = result.markdown || result.answer || 'Справка сформирована.';
    });
  } catch (error) {
    panel.innerHTML = `<button id="close-card" class="close">×</button><div class="empty">Не удалось загрузить карточку: ${esc(error.message || error)}</div>`;
    panel.querySelector('#close-card').onclick = () => panel.classList.remove('open');
  }
}
