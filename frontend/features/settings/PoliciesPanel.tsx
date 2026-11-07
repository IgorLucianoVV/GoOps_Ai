"use client";
import { useEffect, useState } from "react";
import { Lock } from "lucide-react";
import { Badge, Card, ErrorBox } from "@/components/ui";
import { useAction } from "@/hooks/useApi";
import { Saved, SavedInfo } from "./common";

export default function PoliciesPanel({ config, settings, onSaved, canWrite }: { config: any; settings: any; onSaved: () => void; canWrite: boolean }) {
  const action = useAction();
  const [rows, setRows] = useState<any[]>([]);
  const [saved, setSaved] = useState(false);
  const critical: string[] = settings.policies.critical_areas;
  useEffect(() => { setRows(settings.policies.actions.map((a: any) => ({ ...a }))); }, [settings]);
  const isCritical = (a: any) => a.impacted_areas.some((x: string) => critical.includes(x));
  const toggleRole = (i: number, role: string) => setRows(rows.map((r, j) => j !== i ? r : {
    ...r, approver_roles: r.approver_roles.includes(role) ? r.approver_roles.filter((x: string) => x !== role) : [...r.approver_roles, role] }));
  const save = async () => {
    const value: any = {};
    rows.forEach((r) => { value[r.action_type] = { approver_roles: r.approver_roles, requires_approval: isCritical(r) ? true : !!r.requires_approval }; });
    if (await action.run("/settings/config/policies", { value })) { setSaved(true); setTimeout(() => setSaved(false), 2500); onSaved(); }
  };
  return (
    <Card title="Políticas de ações" actions={<SavedInfo section={config.sections.policies} />}
      subtitle={`Ações que impactam ${critical.join(", ")} SEMPRE exigem aprovação humana (bloqueado). Configure quem aprova e se ações internas também exigem aprovação.`}>
      <ErrorBox error={action.error} />
      <div className="space-y-3">
        {rows.map((r, i) => (
          <div key={r.action_type} className="flex flex-wrap items-start justify-between gap-3 rounded-lg border border-ink-700 bg-ink-850 p-3">
            <div className="min-w-60">
              <div className="text-sm font-medium text-white">{r.title}</div>
              <div className="mt-1 flex flex-wrap gap-1">{r.impacted_areas.map((a: string) => <Badge key={a} tone={critical.includes(a) ? "amber" : "gray"}>{a}</Badge>)} <Badge>risco {r.risk}</Badge> <Badge tone="blue">{r.domain}</Badge></div>
            </div>
            <div>
              <div className="label mb-1">Exige aprovação</div>
              {isCritical(r) ? <span className="inline-flex items-center gap-1 text-xs text-amber-300"><Lock size={12} /> obrigatória</span> :
                <label className="flex items-center gap-2 text-sm"><input type="checkbox" disabled={!canWrite} checked={!!r.requires_approval} onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, requires_approval: e.target.checked } : x)))} /> sim</label>}
            </div>
            <div>
              <div className="label mb-1">Papéis aprovadores</div>
              <div className="flex flex-wrap gap-3">
                {config.approver_role_choices.map((role: string) => (
                  <label key={role} className="flex items-center gap-1.5 text-sm"><input type="checkbox" disabled={!canWrite} checked={r.approver_roles.includes(role)} onChange={() => toggleRole(i, role)} /> {role}</label>
                ))}
              </div>
            </div>
          </div>
        ))}
      </div>
      {canWrite && <div className="mt-3 flex items-center gap-3"><button className="btn-primary" disabled={action.busy} onClick={save}>Salvar políticas</button><Saved show={saved} /></div>}
    </Card>
  );
}
