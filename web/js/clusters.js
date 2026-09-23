import { api } from './api.js';
import { money, gid, esc } from './format.js';

export async function clustersView(root) {
  root.innerHTML = '<div class="cluster-grid skeleton"></div>';
  const data = await api.get('/clusters');
  const rows = data.items || data || [];
  root.innerHTML = `<div class="cluster-grid">${rows.map(cluster => `<article class="cluster"><header><span class="cluster-dot"></span><b>Кластер ${gid(cluster.id ?? cluster.cluster_id)}</b><small>${cluster.size ?? cluster.n_nodes ?? 0} узлов</small></header><div class="cluster-stats"><span>seed <b>${cluster.seed_count ?? cluster.n_seed ?? 0}</b></span><span>оборот <b>${money(cluster.turnover_kzt ?? cluster.sum_kzt_internal)}</b></span></div><div class="role-stack">${Object.entries(cluster.roles || cluster.role_counts || {}).map(([role, value]) => `<i class="${role}" style="flex:${value}" title="${role}: ${value}"></i>`).join('')}</div><p>${esc(cluster.hypothesis || 'Гипотеза не сформирована')}</p><div class="gids">${(cluster.top_gids || []).map(value => `<button data-gid="${gid(value)}">${gid(value).slice(-6)}</button>`).join('')}</div><button class="button show-cluster" data-cluster="${gid(cluster.id ?? cluster.cluster_id)}">Показать на графе</button></article>`).join('')}</div>`;
  root.querySelectorAll('[data-gid]').forEach(button => {
    button.onclick = () => { location.href = `?tab=graph&node=${encodeURIComponent(button.dataset.gid)}`; };
  });
  root.querySelectorAll('.show-cluster').forEach(button => {
    button.onclick = () => { location.href = `?tab=graph&cluster=${encodeURIComponent(button.dataset.cluster)}`; };
  });
}
