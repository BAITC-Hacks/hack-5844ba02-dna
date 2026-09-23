import { api } from './api.js';
import { esc } from './format.js';
import { state } from './state.js';

const safe = text => esc(text)
  .replace(/\[gid:([^\]]+)\]/g, (_, value) => `<button class="gid-chip" data-gid="${esc(value)}">${esc(value)}</button>`)
  .replace(/\n/g, '<br>');

export function assistantView(root) {
  if (!state.llmAvailable) {
    root.innerHTML = `<section class="assistant"><div class="empty"><div><h2>AI-ассистент выключен</h2><p>Основная аналитика работает без LLM. Чтобы включить чат, скопируйте <code>.env.example</code> в <code>.env</code>, укажите ключ OpenAI или NVIDIA и перезапустите сервер.</p></div></div></section>`;
    return;
  }

  root.innerHTML = `<section class="assistant"><div id="chat" class="chat"><div class="message bot">Спросите о связях, путях и кластерах. Ответы — гипотезы для проверки.</div></div><div class="examples"><button>Кто собирает деньги с seed?</button><button>Покажи путь между узлами</button><button>Какие консолидаторы в кластере 1?</button></div><form id="chat-form"><textarea placeholder="Сообщение… (Enter — отправить)" rows="2"></textarea><button class="button primary">Отправить</button></form></section>`;
  const form = root.querySelector('form');
  const field = form.querySelector('textarea');
  const chat = root.querySelector('#chat');
  const history = [];

  const send = async text => {
    if (!text.trim()) return;
    chat.insertAdjacentHTML('beforeend', `<div class="message user">${safe(text)}</div><div class="message bot typing">Анализирую…</div>`);
    field.value = '';
    try {
      const result = await api.post('/assistant', { question: text, history });
      history.push({ role: 'user', content: text }, { role: 'assistant', content: result.answer || '' });
      chat.querySelector('.typing').outerHTML = `<div class="message bot">${safe(result.answer || 'Нет ответа')} ${result.tool_calls?.length ? `<details><summary>Вызванные инструменты (${result.tool_calls.length})</summary><pre>${esc(JSON.stringify(result.tool_calls, null, 2))}</pre></details>` : ''}</div>`;
    } catch (error) {
      chat.querySelector('.typing').textContent = `Не удалось получить ответ: ${error.message || error}`;
    }
    chat.scrollTop = chat.scrollHeight;
  };

  form.onsubmit = event => { event.preventDefault(); send(field.value); };
  field.onkeydown = event => {
    if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); send(field.value); }
  };
  root.querySelectorAll('.examples button').forEach(button => { button.onclick = () => send(button.textContent); });
  root.addEventListener('click', event => {
    const button = event.target.closest('[data-gid]');
    if (button) window.focusNode(button.dataset.gid);
  });
}
