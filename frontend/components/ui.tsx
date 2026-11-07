"use client";
import clsx from "clsx";
import Link from "next/link";
import { useId, useState } from "react";
import { AlertTriangle, ArrowDownRight, ArrowUpRight, FlaskConical, HelpCircle, Inbox, Loader2, Minus } from "lucide-react";
import type { ApiError } from "@/services/api";
import { SEVERITY_LABEL, STATUS_LABEL } from "./labels";

export function PageHeader({ title, subtitle, actions, kicker }: { title: string; subtitle?: string; actions?: React.ReactNode; kicker?: string }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        {kicker && <div className="mb-1 text-xs font-semibold uppercase tracking-wider text-coral-300">{kicker}</div>}
        <h1 className="text-2xl font-semibold tracking-tight text-white sm:text-[28px]">{title}</h1>
        {subtitle && <p className="mt-1 max-w-3xl text-sm text-slate-400">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Card({ title, children, className, actions, subtitle, tour }: { title?: React.ReactNode; children: React.ReactNode; className?: string; actions?: React.ReactNode; subtitle?: string; tour?: string }) {
  return (
    <section className={clsx("card p-4", className)} data-tour={tour}>
      {(title || actions) && (
        <div className="mb-3 flex items-start justify-between gap-3">
          <div>
            {title && <h2 className="text-sm font-semibold text-slate-100">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>}
          </div>
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

export function InfoTip({ text, label = "Mais informações" }: { text: React.ReactNode; label?: string }) {
  const id = useId();
  const [open, setOpen] = useState(false);
  return (
    <span className="relative inline-flex">
      <button type="button" aria-label={label} aria-describedby={open ? id : undefined} className="rounded-full text-slate-500 hover:text-brand-400"
        onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)} onFocus={() => setOpen(true)} onBlur={() => setOpen(false)}
        onKeyDown={(e) => { if (e.key === "Escape") setOpen(false); }}>
        <HelpCircle size={14} aria-hidden />
      </button>
      {open && <span id={id} role="tooltip" className="absolute left-1/2 top-6 z-50 w-64 -translate-x-1/2 rounded-lg border border-ink-600 bg-ink-900 p-2.5 text-xs font-normal normal-case tracking-normal text-slate-200 shadow-xl">{text}</span>}
    </span>
  );
}

export function Kpi({ label, value, hint, tone = "default", info, delta, deltaLabel, deltaGoodWhen = "up" }:
  { label: string; value: React.ReactNode; hint?: React.ReactNode; tone?: "default" | "good" | "bad" | "warn"; info?: React.ReactNode;
    delta?: number | null; deltaLabel?: string; deltaGoodWhen?: "up" | "down" }) {
  const color = { default: "text-white", good: "text-emerald-300", bad: "text-rose-300", warn: "text-amber-300" }[tone];
  const hasDelta = delta !== undefined && delta !== null;
  const good = hasDelta && (deltaGoodWhen === "up" ? delta! > 0 : delta! < 0);
  const Icon = !hasDelta || delta === 0 ? Minus : delta! > 0 ? ArrowUpRight : ArrowDownRight;
  return (
    <div className="card p-4">
      <div className="flex items-center gap-1.5"><span className="label">{label}</span>{info && <InfoTip text={info} label={`Sobre: ${label}`} />}</div>
      <div className={clsx("mt-2 text-3xl font-semibold tabular-nums tracking-tight", color)}>{value}</div>
      {hasDelta && (
        <div className={clsx("mt-1 inline-flex items-center gap-1 text-xs font-medium", delta === 0 ? "text-slate-500" : good ? "text-emerald-300" : "text-rose-300")}>
          <Icon size={14} aria-hidden /><span>{delta! > 0 ? "+" : ""}{delta!.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}</span>
          <span className="sr-only">{good ? "(melhora)" : delta === 0 ? "(estável)" : "(piora)"}</span>
          {deltaLabel && <span className="font-normal text-slate-500">{deltaLabel}</span>}
        </div>
      )}
      {hint && <div className="mt-1 text-xs text-slate-500">{hint}</div>}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={clsx("skeleton", className)} />;
}

export function PageSkeleton() {
  return (
    <div role="status" aria-live="polite" className="space-y-4">
      <span className="sr-only">Carregando…</span>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-24" />)}</div>
      <Skeleton className="h-64" />
      <Skeleton className="h-40" />
    </div>
  );
}

const TONES: Record<string, string> = {
  gray: "bg-slate-700/40 text-slate-300 border-slate-600/50",
  green: "bg-emerald-500/10 text-emerald-300 border-emerald-500/30",
  red: "bg-rose-500/10 text-rose-300 border-rose-500/30",
  amber: "bg-amber-500/10 text-amber-300 border-amber-500/30",
  blue: "bg-sky-500/10 text-sky-300 border-sky-500/30",
  violet: "bg-violet-500/10 text-violet-300 border-violet-500/30",
  teal: "bg-teal-500/10 text-teal-300 border-teal-500/30",
};

export function Badge({ children, tone = "gray", className }: { children: React.ReactNode; tone?: keyof typeof TONES | string; className?: string }) {
  return <span className={clsx("inline-flex items-center gap-1 whitespace-nowrap rounded border px-1.5 py-0.5 text-[11px] font-medium", TONES[tone] || TONES.gray, className)}>{children}</span>;
}

export function StatusBadge({ status }: { status: string }) {
  const tone =
    ["resolved", "approved", "executed", "success", "completed", "active", "passed", "closed"].includes(status) ? "green"
    : ["failed", "rejected", "not_resolved"].includes(status) ? "red"
    : ["awaiting_approval", "pending_approval", "waiting", "warning", "pending", "partial"].includes(status) ? "amber"
    : ["investigating", "executing", "running", "monitoring"].includes(status) ? "blue" : "gray";
  return <Badge tone={tone}>{STATUS_LABEL[status] || status}</Badge>;
}

export function SeverityBadge({ severity }: { severity: string }) {
  const tone = { critical: "red", high: "amber", medium: "violet", low: "gray" }[severity] || "gray";
  return <Badge tone={tone}>{SEVERITY_LABEL[severity] || severity}</Badge>;
}

export function DemoBadge({ show = true }: { show?: boolean }) {
  if (!show) return null;
  return <Badge tone="violet"><FlaskConical size={11} aria-hidden /> Dados sintéticos (demonstração)</Badge>;
}

export function Loading({ label = "Carregando…" }: { label?: string }) {
  return <div role="status" aria-live="polite" className="flex items-center gap-2 p-6 text-sm text-slate-400"><Loader2 size={16} className="animate-spin" aria-hidden />{label}</div>;
}

function guidance(error: ApiError): { title: string; hint: string; link?: { href: string; label: string } } {
  const code = error.body?.code;
  if (error.status === 0) return { title: "Sem conexão com a API",
    hint: "Verifique se o backend está rodando (terminal com uvicorn) e se http://localhost:8000/api/health responde. Depois clique em Tentar novamente." };
  if (error.status === 401) return { title: "Sessão expirada ou ausente", hint: "Entre novamente para continuar.", link: { href: "/login", label: "Ir para a tela de entrada" } };
  if (error.status === 403) return { title: "Ação não permitida para o seu perfil", hint: "Peça a um administrador o papel ou domínio necessário (Configurações › Usuários)." };
  if (code === "data_not_ready" || error.status === 409 && /constru|processad/i.test(error.message))
    return { title: "Dados ainda não disponíveis", hint: "Execute o pipeline ou carregue os dados iniciais para gerar os dados.", link: { href: "/lakehouse", label: "Abrir Lakehouse de dados" } };
  if (error.status === 404) return { title: "Item não encontrado", hint: "Ele pode ter sido removido ou o endereço está incorreto." };
  if (error.status === 409) return { title: "Conflito com o estado atual", hint: "Atualize a página para ver o estado mais recente e tente novamente." };
  if (error.status === 422) return { title: "Dados inválidos", hint: "Revise os campos informados." };
  if (error.status === 429) return { title: "Muitas requisições", hint: "Aguarde alguns segundos e tente novamente." };
  if (error.status >= 500) return { title: "Erro interno", hint: "Tente novamente. Se persistir, consulte os logs do servidor." };
  return { title: "Não foi possível concluir a operação", hint: "" };
}

/** Mensagens de erro em linguagem simples, com causa e próximo passo (Heurística 9). */
export function ErrorBox({ error, onRetry }: { error: ApiError | null; onRetry?: () => void }) {
  if (!error) return null;
  const g = guidance(error);
  const soft = error.status === 409 || error.status === 404 || error.status === 403;
  return (
    <div role="alert" className={clsx("mb-4 flex items-start gap-3 rounded-xl border p-4 text-sm", soft ? "border-amber-500/40 bg-amber-950 text-amber-200" : "border-rose-500/40 bg-rose-950 text-rose-200")}>
      <AlertTriangle size={18} className="mt-0.5 shrink-0" aria-hidden />
      <div className="flex-1">
        <div className="font-semibold">{g.title}</div>
        <div className="mt-0.5">{error.message}</div>
        {g.hint && <div className="mt-1 opacity-90">{g.hint}</div>}
        {g.link && <Link className="mt-2 inline-block font-medium underline underline-offset-2" href={g.link.href}>{g.link.label}</Link>}
        {error.body?.details && <details className="mt-2"><summary className="cursor-pointer text-xs opacity-80">Detalhes técnicos</summary><pre className="mt-1 max-h-32 overflow-auto text-xs opacity-80">{JSON.stringify(error.body.details, null, 2)}</pre></details>}
      </div>
      {onRetry && <button className="btn-ghost" onClick={onRetry}>Tentar novamente</button>}
    </div>
  );
}

/** Estados vazios comunicam o status, ensinam e oferecem um caminho direto (NN/g — empty states). */
export function Empty({ title, hint, action }: { title: string; hint?: string; action?: React.ReactNode }) {
  return (
    <div role="status" className="flex flex-col items-center justify-center gap-2 p-8 text-center">
      <span className="grid h-11 w-11 place-items-center rounded-full bg-ink-800 text-slate-500"><Inbox size={20} aria-hidden /></span>
      <div className="text-sm font-medium text-slate-200">{title}</div>
      {hint && <div className="max-w-md text-xs text-slate-500">{hint}</div>}
      {action && <div className="mt-2 flex flex-wrap justify-center gap-2">{action}</div>}
    </div>
  );
}

export interface Column<T> { key: string; label: string; render?: (row: T) => React.ReactNode; className?: string; }

export function DataTable<T extends Record<string, any>>({ columns, rows, empty = "Sem registros", emptyHint, emptyAction, onRowClick, maxHeight, caption }:
  { columns: Column<T>[]; rows: T[]; empty?: string; emptyHint?: string; emptyAction?: React.ReactNode; onRowClick?: (r: T) => void; maxHeight?: number; caption?: string }) {
  if (!rows || rows.length === 0) return <Empty title={empty} hint={emptyHint} action={emptyAction} />;
  return (
    <div className="overflow-auto" style={maxHeight ? { maxHeight } : undefined} tabIndex={maxHeight ? 0 : undefined} aria-label={caption}>
      <table className="table w-full">
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead className="sticky top-0 z-10 bg-ink-900"><tr>{columns.map((c) => <th key={c.key} scope="col" className={c.className}>{c.label}</th>)}</tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} onClick={onRowClick ? () => onRowClick(r) : undefined} onKeyDown={onRowClick ? (e) => { if (e.key === "Enter") onRowClick(r); } : undefined}
              tabIndex={onRowClick ? 0 : undefined} className={onRowClick ? "cursor-pointer" : undefined}>
              {columns.map((c) => <td key={c.key} className={c.className}>{c.render ? c.render(r) : formatCell(r[c.key])}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function formatCell(v: any): React.ReactNode {
  if (v === null || v === undefined) return <span className="text-slate-600">—</span>;
  if (typeof v === "boolean") return v ? "sim" : "não";
  if (typeof v === "number") return v.toLocaleString("pt-BR", { maximumFractionDigits: 2 });
  if (typeof v === "object") return <code className="text-xs text-slate-400">{JSON.stringify(v).slice(0, 80)}</code>;
  return String(v);
}

export function Tabs({ tabs, active, onChange }: { tabs: { key: string; label: string }[]; active: string; onChange: (k: string) => void }) {
  return (
    <div role="tablist" className="mb-4 flex flex-wrap gap-1 border-b border-ink-700">
      {tabs.map((t) => (
        <button key={t.key} role="tab" aria-selected={active === t.key} onClick={() => onChange(t.key)}
          className={clsx("-mb-px border-b-2 px-3 py-2 text-sm", active === t.key ? "border-brand-500 text-white" : "border-transparent text-slate-400 hover:text-slate-200")}>
          {t.label}
        </button>
      ))}
    </div>
  );
}

export function MetricTag({ meta }: { meta?: { metric_key: string; version: string; scope?: string; synthetic?: boolean; synthetic_fields?: string[]; includes_demo_rows?: boolean } }) {
  if (!meta) return null;
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      <Badge tone={meta.scope === "domain" ? "blue" : "teal"} className="font-mono">{meta.metric_key} v{meta.version}</Badge>
      {meta.synthetic && <SyntheticBadge fields={meta.synthetic_fields} demoRows={meta.includes_demo_rows} />}
    </span>
  );
}

/** Sinaliza resultado que depende de campos sintéticos (complemento de demonstração) — nunca apresentado como real. */
export function SyntheticBadge({ fields, demoRows }: { fields?: string[]; demoRows?: boolean }) {
  const parts = [fields?.length ? `campos sintéticos: ${fields.join(", ")}` : "", demoRows ? "inclui registros fictícios" : ""].filter(Boolean);
  return (
    <span title={`Depende de dados sintéticos de demonstração (${parts.join("; ")}).`}>
      <Badge tone="violet"><FlaskConical size={11} aria-hidden /> sintético</Badge>
      <span className="sr-only">Depende de dados sintéticos de demonstração: {parts.join("; ")}</span>
    </span>
  );
}

export function JsonBlock({ value, maxHeight = 240 }: { value: any; maxHeight?: number }) {
  return <pre className="overflow-auto rounded-md bg-ink-950 p-3 text-xs text-slate-300" style={{ maxHeight }}>{JSON.stringify(value, null, 2)}</pre>;
}
