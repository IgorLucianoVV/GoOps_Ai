"use client";
import Link from "next/link";
import { AlertTriangle, Bot, CheckCircle2, CircleDashed, FileText, FlaskConical, Megaphone, Wrench, XCircle } from "lucide-react";
import { fmt } from "@/components/labels";
import { Badge } from "@/components/ui";
import Markdown from "@/features/ask/Markdown";

/* ------------------------------------------------------------------ comparação de versões (diff por palavra) */
type Tok = { t: string; k: "same" | "add" | "del" };
function diffTokens(a: string, b: string): Tok[] {
  const A = a.split(/(\s+)/), B = b.split(/(\s+)/);
  const n = A.length, m = B.length;
  if (n * m > 1_500_000) return [{ t: a, k: "del" }, { t: b, k: "add" }];
  const L: Uint16Array[] = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) L[i][j] = A[i] === B[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
  const out: Tok[] = [];
  let i = 0, j = 0;
  while (i < n && j < m) {
    if (A[i] === B[j]) { out.push({ t: A[i], k: "same" }); i++; j++; }
    else if (L[i + 1][j] >= L[i][j + 1]) out.push({ t: A[i++], k: "del" });
    else out.push({ t: B[j++], k: "add" });
  }
  while (i < n) out.push({ t: A[i++], k: "del" });
  while (j < m) out.push({ t: B[j++], k: "add" });
  return out;
}

export function DiffView({ before, after, beforeLabel = "Publicada", afterLabel = "Rascunho" }:
  { before: string; after: string; beforeLabel?: string; afterLabel?: string }) {
  const toks = diffTokens(before, after);
  const changed = toks.some((x) => x.k !== "same");
  return (
    <div className="rounded-lg border border-ink-700 bg-ink-950 p-3 text-[13px] leading-relaxed">
      <div className="mb-2 flex flex-wrap gap-3 text-xs text-slate-400">
        <span><span className="rounded bg-rose-500/15 px-1 text-rose-300 line-through">removido</span> {beforeLabel}</span>
        <span><span className="rounded bg-emerald-500/15 px-1 text-emerald-300">adicionado</span> {afterLabel}</span>
      </div>
      {!changed ? <p className="text-slate-500">Sem diferenças.</p> : (
        <p className="whitespace-pre-wrap text-slate-300">
          {toks.map((x, i) => x.k === "same" ? <span key={i}>{x.t}</span>
            : x.k === "add" ? <ins key={i} className="rounded bg-emerald-500/15 text-emerald-300 no-underline">{x.t}</ins>
            : <del key={i} className="rounded bg-rose-500/15 text-rose-300">{x.t}</del>)}
        </p>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ verificações automáticas / critérios de aceite */
export function ChecksList({ checks }: { checks?: any[] }) {
  if (!checks?.length) return null;
  const judged = checks.filter((c) => c.ok !== null && c.ok !== undefined);
  const passed = judged.filter((c) => c.ok).length;
  return (
    <div>
      <div className="mb-1 text-xs font-semibold text-slate-300">Verificações: {passed}/{judged.length} aprovadas</div>
      <ul className="space-y-1 text-sm">
        {checks.map((c, i) => (
          <li key={i} className="flex items-start gap-2">
            {c.ok === true ? <CheckCircle2 size={15} className="mt-0.5 shrink-0 text-emerald-400" aria-label="aprovado" />
              : c.ok === false ? <XCircle size={15} className="mt-0.5 shrink-0 text-rose-400" aria-label="reprovado" />
              : <CircleDashed size={15} className="mt-0.5 shrink-0 text-slate-500" aria-label="não avaliado" />}
            <span className="text-slate-200">{c.label}{c.auto && <span className="ml-1 text-[11px] text-slate-500">(automático)</span>}
              {c.detail && <span className="block text-xs text-slate-500">{c.detail}</span>}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function GeneratedBy({ by, cost, ms }: { by?: string; cost?: number | null; ms?: number | null }) {
  const ai = by && by !== "deterministic";
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      {ai ? <Badge tone="violet">Gerado por LLM · {String(by).replace("llm:", "")}</Badge> : <Badge>Sem IA (determinístico)</Badge>}
      {cost != null && <span className="text-xs text-slate-500">US$ {fmt.num(cost, 4)}</span>}
      {ms != null && <span className="text-xs text-slate-500">{fmt.num(ms)} ms</span>}
    </span>
  );
}

/* ------------------------------------------------------------------ rastro passo a passo */
const STEP_ICON: Record<string, any> = { instruction: FileText, llm: Bot, tool: Wrench, decision: Megaphone, action: CheckCircle2,
  fallback: AlertTriangle, dry_run: FlaskConical };

export function RunTrace({ steps }: { steps?: any[] }) {
  if (!steps?.length) return <p className="text-sm text-slate-500">Sem rastro para esta execução.</p>;
  return (
    <ol className="relative space-y-3 border-l border-ink-700 pl-5">
      {steps.map((s, i) => {
        const Icon = STEP_ICON[s.kind] || CircleDashed;
        const tone = s.ok === false ? "text-rose-400" : s.kind === "fallback" ? "text-amber-400" : s.kind === "dry_run" ? "text-sky-400" : "text-brand-500";
        return (
          <li key={i} className="relative">
            <span className={`absolute -left-[29px] top-0 grid h-6 w-6 place-items-center rounded-full border border-ink-700 bg-ink-900 ${tone}`}><Icon size={13} aria-hidden /></span>
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="font-medium text-slate-100">{s.title}</span>
              {s.ok === false && <Badge tone="red">falhou</Badge>}
              {s.meta?.ms != null && <span className="text-xs text-slate-500">{fmt.num(s.meta.ms)} ms</span>}
              {s.meta?.tokens_in != null && <span className="text-xs text-slate-500">{fmt.num(s.meta.tokens_in)} → {fmt.num(s.meta.tokens_out)} tokens</span>}
              {s.meta?.cost_usd != null && <span className="text-xs text-slate-500">US$ {fmt.num(s.meta.cost_usd, 4)}</span>}
              {s.link && <Link className="text-xs text-brand-500 underline underline-offset-2" href={s.link}>abrir</Link>}
            </div>
            {s.meta?.args && Object.keys(s.meta.args).length > 0 && <code className="mt-0.5 block text-xs text-slate-500">{JSON.stringify(s.meta.args)}</code>}
            {s.detail && (s.kind === "instruction" || String(s.detail).length > 160
              ? <details className="mt-1"><summary className="cursor-pointer text-xs text-slate-400">{s.kind === "instruction" ? "ver instrução completa" : "ver resultado"}</summary>
                  <pre className="mt-1 max-h-56 overflow-auto whitespace-pre-wrap rounded bg-ink-950 p-2 text-xs text-slate-300">{s.detail}</pre></details>
              : <p className="mt-0.5 text-xs text-slate-400">{s.detail}</p>)}
          </li>
        );
      })}
    </ol>
  );
}

/* ------------------------------------------------------------------ resultado de execução de agente personalizado */
const OUT_TONE: Record<string, string> = { ok: "green", alert: "red", skipped: "amber", no_data: "gray", error: "red" };
const OUT_LABEL: Record<string, string> = { ok: "OK", alert: "Alerta", skipped: "Ignorado", no_data: "Sem dados", error: "Erro" };

export function AgentRunResult({ r, showTrace = false }: { r: any; showTrace?: boolean }) {
  if (!r) return <p className="text-sm text-slate-500">Ainda não executado.</p>;
  return (
    <div className="space-y-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        {r.dry_run && <Badge tone="blue"><FlaskConical size={11} aria-hidden /> teste — nada gravado</Badge>}
        <Badge tone={OUT_TONE[r.status] || "gray"}>{OUT_LABEL[r.status] || r.status}</Badge>
        {r.generated_by && <GeneratedBy by={r.generated_by} cost={r.cost_usd} />}
        {r.message && <span className="text-slate-300">{r.message}</span>}
      </div>
      {r.fallback_reason && <p className="text-xs text-amber-300">Contingência: {r.fallback_reason}</p>}
      {r.would && <p className="rounded-md border border-sky-500/30 bg-sky-500/5 p-2 text-xs text-sky-300">{r.would}</p>}
      {(r.report_md || r.summary_md) && <div className="rounded-md bg-ink-950 p-3"><Markdown text={r.report_md || r.summary_md} /></div>}
      {r.narrative_md && <div className="rounded-md border border-violet-500/40 p-3"><Markdown text={r.narrative_md} /></div>}
      {r.incidents?.length > 0 && (
        <ul className="space-y-1">{r.incidents.map((i: any) => (
          <li key={i.id}><Link className="text-brand-500 underline underline-offset-2" href={`/incidents/${i.id}`}>{i.title}</Link>{!i.created && <span className="text-xs text-slate-500"> (já aberto)</span>}
            {i.operation && <> · <Link className="text-brand-500 underline underline-offset-2" href="/operations">ação {i.operation.status === "pending_approval" ? "aguardando aprovação" : i.operation.status}</Link></>}</li>))}</ul>
      )}
      <ChecksList checks={r.checks} />
      {showTrace && r.trace && <div><div className="mb-2 text-xs font-semibold text-slate-300">Passo a passo</div><RunTrace steps={r.trace} /></div>}
    </div>
  );
}

/* ------------------------------------------------------------------ indicador de saúde (7 dias) */
export function HealthChips({ h }: { h?: any }) {
  if (!h) return null;
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5 text-xs">
      <Badge>{h.runs} exec. 7d</Badge>
      {h.failed > 0 && <Badge tone="red">{h.failed} falha(s)</Badge>}
      {h.fallback_rate != null && <Badge tone={h.fallback_rate > 50 ? "amber" : "green"} >sem IA {fmt.pct(h.fallback_rate)}</Badge>}
      {h.alerts > 0 && <Badge tone="red">{h.alerts} alerta(s)</Badge>}
    </span>
  );
}
