"use client";
import { useState } from "react";
import { Card, ErrorBox } from "@/components/ui";
import { useAction } from "@/hooks/useApi";
import { Field } from "./common";

export default function DomainsPanel({ domains, onSaved, canWrite }: { domains: any[]; onSaved: () => void; canWrite: boolean }) {
  const action = useAction();
  const [form, setForm] = useState({ key: "", name: "", description: "", owner: "" });
  const create = async () => { if (await action.run("/settings/domains", form)) { setForm({ key: "", name: "", description: "", owner: "" }); onSaved(); } };
  const update = async (key: string, body: any) => { if (await action.run(`/settings/domains/${key}`, body)) onSaved(); };
  return (
    <div className="space-y-5">
      <ErrorBox error={action.error} />
      <Card title="Domínios" subtitle="Domínios organizam Gold de domínio, métricas de domínio e escopo de acesso dos usuários.">
        <div className="space-y-2">
          {domains.map((d) => (
            <div key={d.key} className="grid items-center gap-3 rounded-lg border border-ink-700 bg-ink-850 p-3 md:grid-cols-[120px_1fr_2fr_1fr_140px]">
              <code className="text-xs text-white">{d.key}</code>
              <input aria-label="Nome" className="input" disabled={!canWrite} defaultValue={d.name} onBlur={(e) => e.target.value !== d.name && update(d.key, { name: e.target.value })} />
              <input aria-label="Descrição" className="input" disabled={!canWrite} defaultValue={d.description || ""} onBlur={(e) => e.target.value !== (d.description || "") && update(d.key, { description: e.target.value })} />
              <input aria-label="Responsável" className="input" disabled={!canWrite} placeholder="responsável" defaultValue={d.owner || ""} onBlur={(e) => e.target.value !== (d.owner || "") && update(d.key, { owner: e.target.value })} />
              <select aria-label="Status" className="input" disabled={!canWrite || d.key === "corporate"} value={d.status} onChange={(e) => update(d.key, { status: e.target.value })}>
                <option value="active">ativo</option><option value="planned">planejado</option><option value="inactive">inativo</option>
              </select>
            </div>
          ))}
        </div>
      </Card>
      {canWrite && (
        <Card title="Novo domínio">
          <div className="grid gap-3 md:grid-cols-4">
            <Field label="Chave" hint="minúsculas, ex.: finance"><input className="input w-full" value={form.key} onChange={(e) => setForm({ ...form, key: e.target.value })} /></Field>
            <Field label="Nome"><input className="input w-full" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
            <Field label="Descrição"><input className="input w-full" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></Field>
            <Field label="Responsável"><input className="input w-full" value={form.owner} onChange={(e) => setForm({ ...form, owner: e.target.value })} /></Field>
          </div>
          <button className="btn-primary mt-3" disabled={action.busy || !form.key || !form.name} onClick={create}>Criar domínio</button>
        </Card>
      )}
    </div>
  );
}
