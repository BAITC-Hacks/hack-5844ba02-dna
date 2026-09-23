const n = new Intl.NumberFormat('ru-RU');
export const gid = v => String(v ?? '—');
export const number = v => n.format(Number(v || 0));
export const pct = v => `${new Intl.NumberFormat('ru-RU',{maximumFractionDigits:1}).format(Number(v||0)* (Number(v||0)<=1?100:1))} %`;
export function money(v, precise=false){ v=Number(v||0); if(precise) return `${n.format(v)} KZT`; const a=Math.abs(v); if(a>=1e9)return `${new Intl.NumberFormat('ru-RU',{maximumFractionDigits:1}).format(v/1e9)} млрд KZT`; if(a>=1e6)return `${new Intl.NumberFormat('ru-RU',{maximumFractionDigits:2}).format(v/1e6)} млн KZT`; return `${n.format(v)} KZT`; }
export const esc = s => String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
