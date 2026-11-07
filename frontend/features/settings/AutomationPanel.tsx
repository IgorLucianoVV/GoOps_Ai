"use client";
import { useEffect, useState } from "react";
import { Play } from "lucide-react";
import { fmt } from "@/components/labels";
import { Badge, Card, DataTable, ErrorBox, JsonBlock, StatusBadge } from "@/components/ui";
import { useAction, useApi } from "@/hooks/useApi";
import { useConfirm } from "@/hooks/useConfirm";
import { Field, Saved, SavedInfo, num } from "./common";

const JOB_LABEL: Record<string, string> = { pipeline: "Pipeline de dados (ingestão → Gold)", monitor: "Ciclo de monitoramento (Supervisor)", retention: "Política de retenção", support: "Turno do Agente de Atendimento" };

export default function AutomationPanel({ config, onSaved, canWrite }: { config: any; onSaved: () => void; canWrite: boolean }) {
  const action = useAction();
  const confirm = useConfirm();
  const sched = useApi<any>("/scheduler");
  const [mon, setMon] = useState<any>(config.sections.monitor.value);
  const [sc, setSc] = useState<any>(config.sections.scheduler.value);
  const [ret, setRet] = useState<any>(config.sections.retention.value);
  const [saved, setSaved] = useState<string | null>(null);
  const [preview, setPreview] = useState<any>(null);
  useEffect(() => { setMon(config.sections.monitor.value); setSc(config.sections.scheduler.value); setRet(config.sections.retention.value); }, [config]);

  const save = async (section: string, value: any) => {
    if (await action.run(`/settings/config/${section}`, { value })) { setSaved(section); setTimeout(() => setSaved(null), 2500); onSaved(); sched.reload(); }
  };
  const runNow = async (job: string) => { if (await action.run(`/scheduler/run/${job}`, undefined, undefined, { success: `Tarefa "${JOB_LABEL[job]}" executada` })) sched.reload(); };
  const retention = async (dry: boolean) => {
    if (!dry && !(await confirm({ title: "Aplicar a política de retenção agora?", tone: "danger", confirmLabel: "Aplicar",
      description: "Arquivos Bronze elegíveis, registros antigos de quarentena e logs de LLM serão removidos. Recomenda-se simular antes." }))) return;
    const r = await action.run("/data/retention", { dry_run: dry }, undefined, { success: dry ? "Simulação concluída" : "Retenção aplicada" });
    if (r) setPreview(r);
  };
  const n = (v: any) => (v === null || v === undefined ? "" : String(v));

  return (
    <div className="space-y-5">
      <ErrorBox error={action.error || sched.error} />
      <Card title="Agente Monitor — limiares de detecção" actions={<SavedInfo section={config.sections.monitor} />}>
        <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-5">
          <Field label="Queda de NPS (pontos)" hint="vs. mês anterior ou média de 3 meses"><input className="input w-full" type="number" min="1" disabled={!canWrite} value={n(mon.nps_drop_points)} onChange={(e) => setMon({ ...mon, nps_drop_points: num(e.target.value) })} /></Field>
          <Field label="Amostra mínima"><input className="input w-full" type="number" min="1" disabled={!canWrite} value={n(mon.min_sample)} onChange={(e) => setMon({ ...mon, min_sample: num(e.target.value) })} /></Field>
          <Field label="Aumento de atraso (p.p.)"><input className="input w-full" type="number" min="1" disabled={!canWrite} value={n(mon.carrier_late_increase_pp)} onChange={(e) => setMon({ ...mon, carrier_late_increase_pp: num(e.target.value) })} /></Field>
          <Field label="Razão de detratores por linha"><input className="input w-full" type="number" step="0.1" min="1" disabled={!canWrite} value={n(mon.product_detractor_ratio)} onChange={(e) => setMon({ ...mon, product_detractor_ratio: num(e.target.value) })} /></Field>
          <Field label="Investigar automaticamente"><label className="flex items-center gap-2 pt-1.5 text-sm"><input type="checkbox" disabled={!canWrite} checked={!!mon.auto_investigate} onChange={(e) => setMon({ ...mon, auto_investigate: e.target.checked })} /> após detecção</label></Field>
        </div>
        {canWrite && <div className="mt-3 flex items-center gap-3"><button className="btn-primary" disabled={action.busy} onClick={() => save("monitor", mon)}>Salvar limiares</button><Saved show={saved === "monitor"} /></div>}
      </Card>

      <Card title="Agendador" subtitle="Executa tarefas periodicamente no servidor da API (um único executor por vez, via lease no banco)." actions={<SavedInfo section={config.sections.scheduler} />}>
        <div className="grid gap-3 md:grid-cols-3">
          {(["pipeline", "monitor", "retention", "support"] as const).map((job) => (
            <div key={job} className="rounded-lg border border-ink-700 bg-ink-850 p-3">
              <label className="flex items-center gap-2 text-sm font-medium text-white"><input type="checkbox" disabled={!canWrite} checked={!!sc[`${job}_enabled`]} onChange={(e) => setSc({ ...sc, [`${job}_enabled`]: e.target.checked })} /> {JOB_LABEL[job]}</label>
              <div className="mt-2"><Field label="Intervalo (minutos)"><input className="input w-full" type="number" min={job === "retention" ? 60 : job === "support" ? 1 : 5} disabled={!canWrite} value={n(sc[`${job}_interval_minutes`])} onChange={(e) => setSc({ ...sc, [`${job}_interval_minutes`]: num(e.target.value) })} /></Field></div>
            </div>
          ))}
        </div>
        {canWrite && <div className="mt-3 flex items-center gap-3"><button className="btn-primary" disabled={action.busy} onClick={() => save("scheduler", sc)}>Salvar agendamento</button><Saved show={saved === "scheduler"} /></div>}
        {sched.data && (
          <div className="mt-4">
            <div className="mb-2 text-xs text-slate-500">Executor nesta instância: {sched.data.thread_running ? <Badge tone="green">ativo</Badge> : <Badge tone="amber">inativo (SCHEDULER_ENABLED=false?)</Badge>}</div>
            <DataTable rows={sched.data.jobs} columns={[
              { key: "job", label: "Tarefa", render: (r: any) => JOB_LABEL[r.job] },
              { key: "enabled", label: "Ativo", render: (r: any) => <Badge tone={r.enabled ? "green" : "gray"}>{r.enabled ? "sim" : "não"}</Badge> },
              { key: "interval_minutes", label: "Intervalo (min)" },
              { key: "last_run", label: "Última execução", render: (r: any) => r.last_run ? <span><StatusBadge status={r.last_run.status} /> {fmt.date(r.last_run.started_at)} <span className="text-xs text-slate-500">({r.last_run.triggered_by})</span></span> : "—" },
              { key: "next_run", label: "Próxima", render: (r: any) => r.next_run ? (r.next_run.includes("T") ? fmt.date(r.next_run) : r.next_run) : "—" },
              { key: "run", label: "", render: (r: any) => <button className="btn-ghost" disabled={action.busy} onClick={() => runNow(r.job)}><Play size={13} /> Executar agora</button> },
            ]} />
          </div>
        )}
      </Card>

      <Card title="Política de retenção" actions={<SavedInfo section={config.sections.retention} />}
        subtitle="Bronze só é expurgado quando todos os registros do arquivo existem em execuções posteriores (sem perda no reprocessamento). Auditoria e timelines nunca são expurgadas.">
        <div className="grid max-w-3xl gap-3 md:grid-cols-3">
          <Field label="Bronze (dias)"><input className="input w-full" type="number" min="7" disabled={!canWrite} value={n(ret.bronze_days)} onChange={(e) => setRet({ ...ret, bronze_days: num(e.target.value) })} /></Field>
          <Field label="Quarentena (dias)"><input className="input w-full" type="number" min="7" disabled={!canWrite} value={n(ret.quarantine_days)} onChange={(e) => setRet({ ...ret, quarantine_days: num(e.target.value) })} /></Field>
          <Field label="Logs de LLM/roteamento (dias)"><input className="input w-full" type="number" min="7" disabled={!canWrite} value={n(ret.logs_days)} onChange={(e) => setRet({ ...ret, logs_days: num(e.target.value) })} /></Field>
        </div>
        {canWrite && <div className="mt-3 flex flex-wrap items-center gap-2">
          <button className="btn-primary" disabled={action.busy} onClick={() => save("retention", ret)}>Salvar política</button>
          <button className="btn-ghost" disabled={action.busy} onClick={() => retention(true)}>Simular (sem executar)</button>
          <button className="btn-danger" disabled={action.busy} onClick={() => retention(false)}>Aplicar agora</button>
          <Saved show={saved === "retention"} />
        </div>}
        {preview && <div className="mt-3"><JsonBlock value={preview} maxHeight={220} /></div>}
      </Card>
    </div>
  );
}
