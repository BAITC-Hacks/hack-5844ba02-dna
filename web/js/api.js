import { mockApi } from './mock.js';

const cache = new Map();
const base = '/api';
const demo = new URLSearchParams(location.search).get('mock') === '1';
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

export const invalidate = () => cache.clear();
export const isDemo = () => demo;

export class ApiError extends Error {
  constructor(status, detail) {
    super(detail || `API ${status}`);
    this.status = status;
  }
}

async function request(path, { method = 'GET', body, signal } = {}) {
  const key = `${method}${path}`;
  if (method === 'GET' && cache.has(key)) return structuredClone(cache.get(key));
  if (demo) return mockApi(path, { method, body });

  let lastError;
  for (let attempt = 0; attempt < (method === 'GET' ? 2 : 1); attempt += 1) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 7000);
    try {
      const response = await fetch(base + path, {
        method,
        body: body === undefined ? undefined : JSON.stringify(body),
        headers: { 'content-type': 'application/json' },
        signal: signal || controller.signal,
      });
      clearTimeout(timeout);
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new ApiError(response.status, data.detail);
      if (method === 'GET') cache.set(key, data);
      return structuredClone(data);
    } catch (error) {
      clearTimeout(timeout);
      lastError = error;
      if (signal || error instanceof ApiError || attempt > 0) break;
      await sleep(250);
    }
  }
  throw lastError;
}

export const api = {
  get: (path, options) => request(path, options),
  post: (path, body) => request(path, { method: 'POST', body }),
  health: () => request('/health'),
};
