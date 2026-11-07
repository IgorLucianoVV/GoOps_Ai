"use client";
import { useState } from "react";
import { Check, FlaskConical, GitCompare, History, Lock, RotateCcw, Save, Send, Trash2 } from "lucide-react";
import { fmt } from "@/components/labels";
import { Badge, Card } from "@/components/ui";
import Markdown from "@/features/ask/Markdown";
import { api } from "@/services/api";
import { useAction } from "@/hooks/useApi";
import { useConfirm } from "@/hooks/useConfirm";
import { ChecksList, DiffView, GeneratedBy } from "./parts";

const LEVEL: Record<number, string> = { 1: "modelo pequeno (nível 1)", 2: "LLM econômico (nível 2)", 3: "LLM avançado (nível 3)" };
const who = (s?: string) => String(s || "").replace(/^(user|system):/, "");

function Step({ n, label, state }: { n: number; label: string; state: "done" | "current" | "todo" }) {
  return (
    <li className="flex items-center gap-2">
      <span className={`grid h-6 w-6 place-items-center rounded-full text-xs font-semibold ${state === "done" ? "bg-emerald-500/20 text-emerald-300" : state === "current" ? "bg-brand-600 text-white" : "bg-ink-800 text-slate-500"}`}>
        {state === "done" ? <Check size={13} aria-hidden /> : n}</span>
      <span className={state === "todo" ? "text-slate-500" : "text-slate-200"}>{label}</span>
    </li>
  );
}

/** Teste de uma instrução: resultado, verificações e o prompt exato enviado. */
function TestPanel({ t }: { t: any }) {
  return (
    <div className="mt-3 space-y-3 rounded-lg border border-sky-500/30 bg-sky-500/5 p-3">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <Badge tone="blue"><FlaskConical size={11} aria-hidden /> Teste com dados de exemplo</Badge>
        {t.ran ? <GeneratedBy by={t.generated_by} cost={t.cost_usd} ms={t.latency_ms} /> : <Badge tone="amber">modelo não executado</Badge>}
        <span className="text-xs text-slate-500">{fmt.date(t.tested_at)}</span>
      </div>
      {t.reason && <p className="text-xs text-amber-300">{t.reason}</p>}
      {t.question && <p className="text-xs text-slate-400">Pergunta de teste: “{t.question}”</p>}
      {t.output && <div className="rounded-md bg-ink-950 p-3 text-sm"><Markdown text={t.output} /></div>}
      <ChecksList checks={t.checks} />
      {(t.prompt || t.system_prompt) && (
        <details><summary className="cursor-pointer text-xs text-slate-400">Ver exatamente o que foi enviado ao modelo</summary>
          {t.system_prompt && <><div className="mt-2 text-[11px] font-semibold uppercase text-slate-500">Instrução de sistema</div>
            <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap rounded bg-ink-950 p-2 text-xs text-slate-300">{t.system_prompt}</pre></>}
          {t.prompt && <><div className="mt-2 text-[11px] font-semibold uppercase text-slate-500">Mensagem (instrução + evidências de exemplo)</div>
            <pre className="mt-1 max-h-64 overflow-auto whitespace-pre-wrap rounded bg-ink-950 p-2 text-xs text-slate-300">{t.prompt}</pre></>}
        </details>
      )}
    </div>
  );
}

/** Uma tarefa de IA de um agente nativo: Editar (rascunho) → Testar → Publicar, com comparação e histórico. */
export default function InstructionEditor({ item, canEdit, onSaved }: { item: any; canEdit: boolean; onSaved: () => void }) {
  const action = useAction();
  const confirm = useConfirm();
  const draft = item.draft;
  const base = draft?.text ?? item.text;
  const [text, setText] = useState<string>(base);
  const [note, setNote] = useState<string>(draft?.note || "");
  const [question, setQuestion] = useState<string>(item.sample_question || "");
  const [test, setTest] = useState<any>(draft?.last_test?.tested_text === draft?.text ? draft?.last_test : null);
  const [showDiff, setShowDiff] = useState(false);
  const [hist, setHist] = useState<any[] | null>(null);
  const [histDiff, setHistDiff] = useState<number | null>(null);
  const dirty = text.trim() !== base.trim();
  const hasChanges = dirty || !!draft;
  const testedCurrent = !!test && test.tested_text === text.trim();
  const id = `ins-${item.slot}`;
  const step = !hasChanges ? 0 : dirty ? 1 : testedCurrent ? 3 : 2;

  const saveDraft = async (silent = false) => {
    const r = await action.run(`/agents/instructions/${item.slot}/draft`, { text, note: note || null }, undefined,
      silent ? undefined : { success: "Rascunho salvo", successDescription: "Os agentes continuam usando a versão publicada até você publicar." });
    if (r) onSaved();
    return r;
  };
  const runTest = async () => {
    if (dirty && !(await saveDraft(true))) return;
    const r = await action.run(`/agents/instructions/${item.slot}/test`, { text, question: item.system ? question : null }, undefined,
      { success: "Teste concluído" });
    if (r) { setTest(r); onSaved(); }
  };
  const publish = async () => {
    const warn = !testedCurrent ? "Este rascunho ainda não foi testado." : test?.checks_ok === false ? "O último teste reprovou em alguma verificação." : null;
    if (!(await confirm({ title: `Publicar “${item.label}”?`, tone: warn ? "danger" : "primary", confirmLabel: "Publicar",
      description: `${warn ? warn + " " : ""}A nova versão passa a valer na próxima execução do agente. Você pode restaurar a anterior a qualquer momento.` }))) return;
    if (dirty && !(await saveDraft(true))) return;
    if (await action.run(`/agents/instructions/${item.slot}/publish`, {}, undefined, { success: "Instrução publicada" })) { setTest(null); setHist(null); onSaved(); }
  };
  const discard = async () => {
    if (!(await confirm({ title: "Descartar o rascunho?", description: "Volta para o texto publicado.", confirmLabel: "Descartar", tone: "danger" }))) return;
    if (draft) { if (!(await action.run(`/agents/instructions/${item.slot}/draft/discard`, {}))) return; onSaved(); }
    setText(item.text); setNote(""); setTest(null);
  };
  const reset = async () => {
    if (!(await confirm({ title: "Restaurar a instrução padrão?", description: "Uma nova versão publicada é criada com o texto original; o histórico é mantido.", confirmLabel: "Restaurar" }))) return;
    if (await action.run(`/agents/instructions/${item.slot}/reset`, {}, undefined, { success: "Padrão restaurado" })) { setHist(null); onSaved(); }
  };
  const restore = async (v: number) => {
    if (await action.run(`/agents/instructions/${item.slot}/restore`, { version: v }, undefined, { success: `Versão ${v} publicada novamente` })) { setHist(null); onSaved(); }
  };
  const loadHistory = async () => {
    if (hist) { setHist(null); return; }
    try { setHist((await api.get<any[]>(`/agents/instructions/${item.slot}/history`)).data); } catch { setHist([]); }
  };

  return (
    <Card title={item.label} subtitle={item.when}
      actions={<span className="inline-flex flex-wrap items-center gap-1.5">
        <Badge tone="violet">{LEVEL[item.level] || `nível ${item.level}`}</Badge>
        {item.is_default ? <Badge>publicada: padrão</Badge> : <Badge tone="teal">publicada: v{item.version}</Badge>}
        {hasChanges && <Badge tone="amber">rascunho não publicado</Badge>}
      </span>}>
      {canEdit && hasChanges && (
        <ol className="mb-3 flex flex-wrap gap-x-6 gap-y-2 text-sm" aria-label="Etapas para publicar">
          <Step n={1} label="Editar" state={step > 1 ? "done" : "current"} />
          <Step n={2} label="Testar" state={step > 2 ? "done" : step === 2 ? "current" : "todo"} />
          <Step n={3} label="Publicar" state={step === 3 ? "current" : "todo"} />
        </ol>
      )}
      <label htmlFor={id} className="label">{item.system ? "Instrução de sistema (editável)" : "Instrução da tarefa (editável)"}</label>
      <textarea id={id} className="input mt-1 w-full font-mono text-[13px] leading-relaxed" rows={item.system ? 14 : 3}
        value={text} onChange={(e) => setText(e.target.value)} readOnly={!canEdit} maxLength={4000} />
      <div className="mt-1 flex justify-between text-xs text-slate-500">
        <span>{Object.keys(item.placeholders || {}).length > 0 && <>Marcadores: {Object.entries(item.placeholders).map(([k, v]) => <code key={k} className="mr-2" title={String(v)}>{`{${k}}`}</code>)}</>}
          {draft && !dirty && <>Rascunho salvo por {who(draft.updated_by)} em {fmt.date(draft.updated_at)}</>}</span>
        <span>{text.length}/4000</span>
      </div>
      {showDiff && <div className="mt-2"><DiffView before={item.text} after={text} /></div>}
      {item.fixed && (
        <div className="mt-3 rounded-lg border border-ink-700 bg-ink-950 p-3 text-xs text-slate-400">
          <div className="mb-1 flex items-center gap-1.5 font-semibold text-slate-300"><Lock size={12} aria-hidden /> Regras fixas (sempre anexadas, não editáveis)</div>
          <p className="whitespace-pre-line">{item.fixed}</p>
        </div>
      )}
      {canEdit && (
        <>
          {item.system && (
            <label className="mt-3 block"><span className="label">Pergunta para o teste</span>
              <input className="input mt-1 w-full" value={question} maxLength={300} onChange={(e) => setQuestion(e.target.value)} /></label>
          )}
          {hasChanges && (
            <label className="mt-3 block"><span className="label">Motivo da mudança (vai para o histórico)</span>
              <input className="input mt-1 w-full" value={note} maxLength={300} onChange={(e) => setNote(e.target.value)} placeholder="Ex.: resumo mais curto para a diretoria" /></label>
          )}
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <button className="btn-ghost" disabled={action.busy || !dirty || text.trim().length < 10} onClick={() => saveDraft()}><Save size={14} /> Salvar rascunho</button>
            <button className={step === 2 ? "btn-primary" : "btn-ghost"} disabled={action.busy || text.trim().length < 10} onClick={runTest}>
              <FlaskConical size={14} /> {action.busy ? "Executando…" : "Testar"}</button>
            <button className={step === 3 ? "btn-primary" : "btn-ghost"} disabled={action.busy || !hasChanges || text.trim().length < 10} onClick={publish}><Send size={14} /> Publicar</button>
            {hasChanges && <button className="btn-ghost" onClick={() => setShowDiff(!showDiff)} aria-pressed={showDiff}><GitCompare size={14} /> {showDiff ? "Ocultar comparação" : "Comparar com a publicada"}</button>}
            {hasChanges && <button className="btn-ghost" disabled={action.busy} onClick={discard}><Trash2 size={14} /> Descartar</button>}
            {!hasChanges && !item.is_default && <button className="btn-ghost" disabled={action.busy} onClick={reset}><RotateCcw size={14} /> Restaurar padrão</button>}
          </div>
          {!hasChanges && <p className="mt-2 text-xs text-slate-500">Edite o texto para criar um rascunho, ou use “Testar” para ver como a versão publicada responde a um exemplo.</p>}
        </>
      )}
      {test && <TestPanel t={test} />}
      <div className="mt-3 flex items-center gap-3 text-xs text-slate-500">
        {item.updated_at && <span>Publicada em {fmt.date(item.updated_at)} por {who(item.updated_by)}</span>}
        {item.version > 0 && <button className="inline-flex items-center gap-1 text-brand-500 underline-offset-2 hover:underline" onClick={loadHistory} aria-expanded={!!hist}>
          <History size={12} aria-hidden /> {hist ? "Ocultar histórico" : "Ver histórico"}</button>}
      </div>
      {hist && (
        <ol className="mt-2 space-y-2">
          {hist.map((h) => (
            <li key={h.version} className="rounded-lg border border-ink-700 p-2 text-xs">
              <div className="flex flex-wrap items-center gap-2 text-slate-400">
                <strong className="text-slate-200">v{h.version}</strong>{h.version === item.version && <Badge tone="teal">em uso</Badge>}{!!h.is_default && <Badge>padrão</Badge>}
                <span>{fmt.date(h.created_at)} · {who(h.created_by)}</span>{h.note && <span>— {h.note}</span>}
                <span className="ml-auto inline-flex gap-3">
                  {h.version !== item.version && <button className="text-brand-500 hover:underline" onClick={() => setHistDiff(histDiff === h.version ? null : h.version)}>{histDiff === h.version ? "Ocultar diferenças" : "Comparar com a atual"}</button>}
                  {canEdit && h.version !== item.version && <button className="text-brand-500 hover:underline" disabled={action.busy} onClick={() => restore(h.version)}>Restaurar esta versão</button>}
                </span>
              </div>
              {histDiff === h.version ? <div className="mt-1"><DiffView before={h.text} after={item.text} beforeLabel={`v${h.version}`} afterLabel="atual" /></div>
                : <pre className="mt-1 max-h-32 overflow-auto whitespace-pre-wrap text-slate-300">{h.text}</pre>}
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}
