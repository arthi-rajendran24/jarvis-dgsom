export async function api<T = any>(path: string, body?: unknown): Promise<T> {
  const r = await fetch('/api' + path, body === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json','X-Jarvis-Client':'ui'},body:JSON.stringify(body)});
  if (!r.ok) { const data = await r.json().catch(()=>({detail:'The local server is unavailable.'})); throw new Error(typeof data.detail === 'string' ? data.detail : 'Please check the fields and try again.'); }
  return r.json();
}
