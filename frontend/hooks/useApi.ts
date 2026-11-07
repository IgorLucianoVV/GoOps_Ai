"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, type Query } from "@/services/api";
import { useToast } from "./useToast";

export interface ActionOptions { success?: string; successDescription?: string; silentError?: boolean; }

export function useApi<T = any>(path: string | null, query?: Query) {
  const [data, setData] = useState<T | null>(null);
  const [meta, setMeta] = useState<Record<string, any>>({});
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState<boolean>(!!path);
  const key = JSON.stringify(query || {});
  const seq = useRef(0);

  const load = useCallback(async () => {
    if (!path) return;
    const id = ++seq.current;
    setLoading(true);
    setError(null);
    try {
      const res = await api.get<T>(path, JSON.parse(key));
      if (id === seq.current) { setData(res.data); setMeta(res.meta || {}); }
    } catch (e) {
      if (id === seq.current) setError(e as ApiError);
    } finally {
      if (id === seq.current) setLoading(false);
    }
  }, [path, key]);

  useEffect(() => { load(); }, [load]);
  return { data, meta, error, loading, reload: load };
}

export function useAction<T = any>() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const toast = useToast();
  const run = useCallback(async (path: string, body?: unknown, query?: Query, opts?: ActionOptions): Promise<T | null> => {
    setBusy(true);
    setError(null);
    try {
      const res = await api.post<T>(path, body, query);
      if (opts?.success) toast.push({ tone: "success", title: opts.success, description: opts.successDescription });
      return res.data;
    } catch (e) {
      const err = e as ApiError;
      setError(err);
      if (!opts?.silentError) toast.push({ tone: "error", title: "Não foi possível concluir", description: err.message });
      return null;
    } finally {
      setBusy(false);
    }
  }, [toast]);
  return { run, busy, error, clearError: () => setError(null) };
}
