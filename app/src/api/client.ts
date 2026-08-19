// Cliente da API local do motor. No Electron, baseUrl/token vêm da preload bridge;
// no navegador (dev), de VITE_ENGINE_URL/VITE_ENGINE_TOKEN ou localStorage.

export interface EngineInfo {
  baseUrl: string;
  token: string;
}

declare global {
  interface Window {
    realOficial?: {
      getEngine(): Promise<{ baseUrl: string; token: string; port: number } | null>;
      pickVideoFile(): Promise<string | null>;
      pickImageFile(): Promise<string | null>;
      pickDirectory(): Promise<string | null>;
      openPath(p: string): Promise<string>;
      showInFolder(p: string): Promise<void>;
      openExternal(url: string): Promise<void>;
    };
  }
}

let cached: EngineInfo | null = null;

export async function engine(): Promise<EngineInfo> {
  if (cached) return cached;
  if (window.realOficial) {
    const info = await window.realOficial.getEngine();
    if (!info) throw new Error("Motor ainda não inicializado");
    cached = { baseUrl: info.baseUrl, token: info.token };
    return cached;
  }
  const baseUrl = import.meta.env.VITE_ENGINE_URL
    ?? localStorage.getItem("engine_url") ?? "http://127.0.0.1:8756";
  const token = import.meta.env.VITE_ENGINE_TOKEN
    ?? localStorage.getItem("engine_token") ?? "";
  cached = { baseUrl, token };
  return cached;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const { baseUrl, token } = await engine();
  const res = await fetch(`${baseUrl}${path}`, {
    ...init,
    headers: {
      ...(init?.body && !(init.body instanceof FormData)
        ? { "Content-Type": "application/json" } : {}),
      Authorization: `Bearer ${token}`,
      ...init?.headers,
    },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? JSON.stringify(body);
    } catch {
      /* corpo não-JSON */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const get = <T,>(path: string) => api<T>(path);
export const post = <T,>(path: string, body?: unknown) =>
  api<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
export const patch = <T,>(path: string, body: unknown) =>
  api<T>(path, { method: "PATCH", body: JSON.stringify(body) });
export const del = <T,>(path: string) => api<T>(path, { method: "DELETE" });

export async function mediaUrl(path: string): Promise<string> {
  const { baseUrl, token } = await engine();
  const sep = path.includes("?") ? "&" : "?";
  return `${baseUrl}${path}${sep}token=${encodeURIComponent(token)}`;
}
