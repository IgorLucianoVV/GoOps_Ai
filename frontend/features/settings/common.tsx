"use client";
import { CheckCircle2 } from "lucide-react";
import { fmt } from "@/components/labels";
import { Badge } from "@/components/ui";

export function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      <div className="mt-1">{children}</div>
      {hint && <span className="mt-0.5 block text-[11px] text-slate-500">{hint}</span>}
    </label>
  );
}

export function SavedInfo({ section }: { section?: { customized: boolean; updated_at: string | null; updated_by: string | null } }) {
  if (!section) return null;
  return section.customized
    ? <Badge tone="teal">configurado na interface · {fmt.date(section.updated_at)} · {section.updated_by}</Badge>
    : <Badge>valores do ambiente/padrão</Badge>;
}

export function Saved({ show }: { show: boolean }) {
  if (!show) return null;
  return <span role="status" className="inline-flex items-center gap-1 text-xs text-emerald-300"><CheckCircle2 size={13} /> Salvo</span>;
}

export const num = (v: string) => (v === "" ? null : Number(v));
