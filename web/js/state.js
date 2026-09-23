let saved = 'light';
try { saved = localStorage.getItem('trace-theme') || 'light'; } catch {}

export const state = new Proxy({
  tab: 'graph', node: null, cluster: null, mode: 'all', threshold: 0,
  review: [], theme: saved, outLoaded: false, llmAvailable: false,
}, {
  set(target, key, value) {
    const old = target[key];
    target[key] = value;
    if (old !== value) window.dispatchEvent(new CustomEvent('state', { detail: { key, value } }));
    return true;
  },
});

export const watch = (key, fn) => window.addEventListener('state', event => {
  if (event.detail.key === key) fn(event.detail.value);
});
