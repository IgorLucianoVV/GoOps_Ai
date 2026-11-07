"use client";
import { useState } from "react";
import { UserPlus } from "lucide-react";
import { fmt, ROLE_LABEL } from "@/components/labels";
import { Badge, Card, ErrorBox } from "@/components/ui";
import { useAction, useApi } from "@/hooks/useApi";
import { Field } from "./common";

const ROLES = ["admin", "data_owner", "data_steward", "domain_owner", "data_analyst", "viewer"];

export default function UsersPanel({ domains, canWrite }: { domains: any[]; canWrite: boolean }) {
  const users = useApi<any[]>("/settings/users");
  const action = useAction();
  const [form, setForm] = useState({ email: "", name: "", role: "viewer", domains: ["*"] as string[], password: "" });
  const [pwd, setPwd] = useState<Record<string, string>>({});
  const domainKeys = ["*", ...domains.map((d) => d.key)];

  const create = async () => { if (await action.run("/settings/users", form)) { setForm({ ...form, email: "", name: "", password: "" }); users.reload(); } };
  const update = async (id: string, body: any) => { if (await action.run(`/settings/users/${id}`, body)) users.reload(); };
  const resetPwd = async (id: string) => { if (await action.run(`/settings/users/${id}/password`, { password: pwd[id] })) setPwd({ ...pwd, [id]: "" }); };
  const toggleDomain = (list: string[], d: string) => (d === "*" ? ["*"] : (list.includes(d) ? list.filter((x) => x !== d) : [...list.filter((x) => x !== "*"), d]));

  return (
    <div className="space-y-5">
      <ErrorBox error={action.error || users.error} />
      {canWrite && (
        <Card title="Novo usuário">
          <div className="grid gap-3 md:grid-cols-5">
            <Field label="Nome"><input className="input w-full" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
            <Field label="E-mail"><input className="input w-full" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field>
            <Field label="Papel"><select className="input w-full" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>{ROLES.map((r) => <option key={r} value={r}>{ROLE_LABEL[r] || r}</option>)}</select></Field>
            <Field label="Senha inicial" hint="mín. 8 caracteres"><input className="input w-full" type="password" autoComplete="new-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></Field>
            <Field label="Domínios">
              <div className="flex flex-wrap gap-2 pt-1">{domainKeys.map((d) => <label key={d} className="flex items-center gap-1 text-xs"><input type="checkbox" checked={form.domains.includes(d)} onChange={() => setForm({ ...form, domains: toggleDomain(form.domains, d) })} />{d === "*" ? "todos" : d}</label>)}</div>
            </Field>
          </div>
          <button className="btn-primary mt-3" disabled={action.busy || !form.email || !form.name || form.password.length < 8} onClick={create}><UserPlus size={14} /> Criar usuário</button>
        </Card>
      )}
      <Card title="Usuários">
        <div className="space-y-2">
          {(users.data || []).map((u) => (
            <div key={u.id} className="grid items-center gap-3 rounded-lg border border-ink-700 bg-ink-850 p-3 lg:grid-cols-[1.4fr_1fr_1.6fr_auto_1.2fr]">
              <div><div className="text-sm text-white">{u.name} {u.is_demo && <Badge tone="violet">demo</Badge>}</div><div className="text-xs text-slate-500">{u.email} · criado {fmt.day(u.created_at)}</div></div>
              <select aria-label="Papel" className="input" disabled={!canWrite} value={u.role} onChange={(e) => update(u.id, { role: e.target.value })}>{ROLES.map((r) => <option key={r} value={r}>{ROLE_LABEL[r] || r}</option>)}</select>
              <div className="flex flex-wrap gap-2">{domainKeys.map((d) => <label key={d} className="flex items-center gap-1 text-xs"><input type="checkbox" disabled={!canWrite} checked={u.domains.includes(d)} onChange={() => update(u.id, { domains: toggleDomain(u.domains, d) })} />{d === "*" ? "todos" : d}</label>)}</div>
              <label className="flex items-center gap-1.5 text-sm"><input type="checkbox" disabled={!canWrite} checked={u.active} onChange={(e) => update(u.id, { active: e.target.checked })} /> ativo</label>
              {canWrite ? <div className="flex gap-1"><input aria-label="Nova senha" className="input w-full" type="password" autoComplete="new-password" placeholder="nova senha" value={pwd[u.id] || ""} onChange={(e) => setPwd({ ...pwd, [u.id]: e.target.value })} /><button className="btn-ghost" disabled={action.busy || (pwd[u.id] || "").length < 8} onClick={() => resetPwd(u.id)}>Redefinir</button></div> : <span />}
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
