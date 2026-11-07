import type { ApiErrorBody, Envelope } from "@/types/api";

// Padrão: "/api" (mesma origem, via proxy do Next.js — ver next.config.mjs). Pode ser sobrescrito por NEXT_PUBLIC_API_URL.
export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "/api").replace(/\/$/, "");

export class ApiError extends Error {
  status: number;
  body?: ApiErrorBody;
  constructor(status: number, body?: ApiErrorBody) {
    super(body?.message || `Erro HTTP ${status}`);
    this.status = status;
    this.body = body;
  }
}

/** A sessão fica em cookie httpOnly (inacessível ao JavaScript). Para requisições que alteram estado,
 *  enviamos o token CSRF (cookie não-httpOnly "goops_csrf") no cabeçalho X-CSRF-Token (double-submit). */
function csrfToken(): string | null {
  if (typeof document === "undefined") return null;
  const m = document.cookie.match(/(?:^|;\s*)goops_csrf=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : null;
}

export type Query = Record<string, string | number | boolean | string[] | undefined | null>;

export function buildQuery(q?: Query): string {
  if (!q) return "";
  const p = new URLSearchParams();
  Object.entries(q).forEach(([k, v]) => {
    if (v === undefined || v === null || v === "") return;
    if (Array.isArray(v)) v.forEach((x) => p.append(k, x));
    else p.append(k, String(v));
  });
  const s = p.toString();
  return s ? `?${s}` : "";
}

async function request<T>(method: "GET" | "POST", path: string, body?: unknown, query?: Query): Promise<Envelope<T>> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (method !== "GET") {
    const csrf = csrfToken();
    if (csrf) headers["X-CSRF-Token"] = csrf;
  }
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}${buildQuery(query)}`, {
      method, headers, credentials: "include", cache: "no-store",
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, { code: "network_error", message: `Não foi possível conectar à API (${API_URL}).` });
  }
  const isJson = (res.headers.get("content-type") || "").includes("application/json");
  const json = isJson ? await res.json().catch(() => ({})) : {};
  if (!res.ok && !isJson && res.status >= 500) {
    // resposta do proxy do Next.js quando o backend não está no ar
    throw new ApiError(0, { code: "network_error", message: "O backend não respondeu (a API está em execução na porta 8000?)." });
  }
  if (!res.ok) throw new ApiError(res.status, json?.error);
  return json as Envelope<T>;
}

export const api = {
  get: <T = any>(path: string, query?: Query) => request<T>("GET", path, undefined, query),
  post: <T = any>(path: string, body?: unknown, query?: Query) => request<T>("POST", path, body ?? {}, query),
};
