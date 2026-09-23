import { Chart } from 'chart.js';
import { api } from './api.js';

let charts = [];
const labels = {
  by_priority: 'По приоритету',
  by_degree: 'По степени',
  by_priority_nonseed: 'По приоритету, без seed',
  by_degree_nonseed: 'По степени, без seed',
  random: 'Случайно',
};
const colors = ['#50bedf', '#9fb0be', '#e6bd4f', '#a979e8', '#627689', '#36b88b'];

function dropPercent(values, index) {
  const base = Number(values?.[0] || 0);
  const current = Number(values?.[index] || 0);
  return base ? Math.round((base - current) / base * 100) : 0;
}

export async function resilienceView(root) {
  charts.forEach(chart => chart.destroy());
  charts = [];
  const data = await api.get('/resilience');
  const removed = data.n_removed || data.removed || [];
  const strategies = (data.strategies || Object.keys(data).filter(key => data[key]?.lwcc_size && data[key]?.seed_reachable))
    .filter(key => data[key]?.lwcc_size && data[key]?.seed_reachable);
  if (!removed.length || !strategies.length) {
    root.innerHTML = '<div class="empty">Данные появятся после расширения пайплайна.</div>';
    return;
  }

  const top20 = removed.indexOf(20);
  const summary = top20 < 0 ? '' : `Удаление топ-20: −${dropPercent(data.by_priority?.lwcc_size, top20)}% связности (по степени −${dropPercent(data.by_degree?.lwcc_size, top20)}%, случайно −${dropPercent(data.random?.lwcc_size, top20)}%)`;
  root.innerHTML = `<section class="resilience"><p class="insight">Чем быстрее падает кривая, тем точнее ранжирование выделяет несущие узлы.</p><div class="chart-grid"><article><h2>Размер LWCC</h2><canvas id="lwcc"></canvas></article><article><h2>Достижимость seed</h2><canvas id="seed"></canvas></article></div><p class="notice">${summary}</p></section>`;

  const css = getComputedStyle(document.documentElement);
  const make = (selector, key) => {
    const datasets = strategies.map((strategy, index) => ({
      label: labels[strategy] || strategy,
      data: data[strategy][key],
      borderColor: colors[index % colors.length],
      borderWidth: strategy === 'by_priority' ? 3 : 1.5,
      pointRadius: 2,
      tension: .25,
    }));
    charts.push(new Chart(root.querySelector(selector), {
      type: 'line',
      data: { labels: removed, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: { legend: { labels: { color: css.getPropertyValue('--fg').trim() } } },
        scales: {
          x: { ticks: { color: css.getPropertyValue('--fg-muted').trim() }, grid: { color: css.getPropertyValue('--border').trim() } },
          y: { beginAtZero: true, ticks: { color: css.getPropertyValue('--fg-muted').trim() }, grid: { color: css.getPropertyValue('--border').trim() } },
        },
      },
    }));
  };
  make('#lwcc', 'lwcc_size');
  make('#seed', 'seed_reachable');
}
