"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { Eye, EyeOff, Loader2 } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";

export default function LoginPage() {
  const { login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("admin@goops.local");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true); setError(null);
    try { await login(email, password); router.replace("/"); }
    catch (err: any) { setError(err?.status === 401 ? "E-mail ou senha incorretos." : (err?.message || "Falha ao entrar")); }
    finally { setBusy(false); }
  };

  return (
    <div className="grid min-h-screen lg:grid-cols-[1.1fr_1fr]">
      <section className="geo-bg relative hidden flex-col justify-between p-12 text-[#FFFFFF] lg:flex" aria-hidden="true">
        <div className="flex items-center gap-2.5">
          <span className="relative h-10 w-10 overflow-hidden rounded-xl bg-accent-400">
            <span className="absolute -right-2.5 -top-2.5 h-7 w-7 rounded-full bg-coral-400" />
            <span className="absolute bottom-2 left-2 h-4 w-4 rotate-45 rounded-[3px] bg-navy-900" />
          </span>
          <span className="text-lg font-semibold">GoOps AI</span>
        </div>
        <div className="max-w-md">
          <h2 className="text-4xl font-semibold leading-tight">Dados confiáveis.<br />Decisões rápidas.<br /><span className="text-accent-400">Ações supervisionadas.</span></h2>
          <p className="mt-4 text-[#D4D4D8]">Lakehouse de dados governado, métricas oficiais e agentes de IA que investigam e propõem ações — sempre com aprovação humana.</p>
        </div>
        <p className="text-xs text-[#A1A1AA]">Operational Intelligence Platform</p>
      </section>
      <main className="grid place-items-center bg-ink-950 p-6">
        <form onSubmit={submit} className="w-full max-w-sm space-y-5" aria-labelledby="login-title" noValidate>
          <div>
            <h1 id="login-title" className="text-2xl font-semibold text-white">Entrar</h1>
            <p className="mt-1 text-sm text-slate-400">Use suas credenciais corporativas.</p>
          </div>
          <label className="block"><span className="text-sm font-medium text-slate-200">E-mail</span>
            <input className="input mt-1.5 h-11 w-full" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" required /></label>
          <label className="block"><span className="text-sm font-medium text-slate-200">Senha</span>
            <span className="relative mt-1.5 block">
              <input className="input h-11 w-full pr-11" type={show ? "text" : "password"} value={password} onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password" required aria-invalid={!!error} aria-describedby={error ? "login-error" : undefined} />
              <button type="button" onClick={() => setShow(!show)} className="absolute right-1.5 top-1.5 rounded-md p-2 text-slate-500 hover:text-slate-200"
                aria-label={show ? "Ocultar senha" : "Mostrar senha"} aria-pressed={show}>{show ? <EyeOff size={16} aria-hidden /> : <Eye size={16} aria-hidden />}</button>
            </span></label>
          {error && <div id="login-error" role="alert" className="rounded-lg border border-rose-500/40 bg-rose-950 p-3 text-sm text-rose-200">{error}</div>}
          <button className="btn-primary h-11 w-full" disabled={busy || !email || !password}>{busy && <Loader2 size={15} className="animate-spin" aria-hidden />}Entrar</button>
          <p className="text-xs text-slate-500">Ambiente de demonstração: senha em DEMO_ADMIN_PASSWORD (.env) ou em <code>var/demo_credentials.txt</code>. Sessão protegida por cookie httpOnly.</p>
        </form>
      </main>
    </div>
  );
}
