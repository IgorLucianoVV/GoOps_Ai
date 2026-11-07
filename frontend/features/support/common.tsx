"use client";
import { Mail, Megaphone, MessageCircle } from "lucide-react";
import { Badge } from "@/components/ui";

export const CHANNEL: Record<string, { label: string; tone: string; icon: any }> = {
  whatsapp: { label: "WhatsApp", tone: "green", icon: MessageCircle },
  email: { label: "E-mail", tone: "blue", icon: Mail },
  reclameaqui: { label: "Reclame Aqui", tone: "red", icon: Megaphone },
};
export const URGENCY: Record<string, { label: string; tone: string }> = {
  baixa: { label: "Baixa", tone: "gray" }, media: { label: "Média", tone: "violet" },
  alta: { label: "Alta", tone: "amber" }, critica: { label: "Crítica", tone: "red" },
};
export const VERACITY: Record<string, { label: string; tone: string; hint: string }> = {
  consistente: { label: "Consistente", tone: "green", hint: "Os dados sustentam a reclamação: ações de reparação liberadas (com a política de aprovação)." },
  inconclusiva: { label: "Inconclusiva", tone: "amber", hint: "Faltam evidências: o agente indica o que verificar (foto, comprovante de entrega)." },
  inconsistente: { label: "Não sustentada", tone: "red", hint: "Os dados não sustentam a reclamação. Vai para uma pessoa com as evidências — nunca é negada automaticamente." },
  nao_aplicavel: { label: "Não se aplica", tone: "gray", hint: "Assunto que não pede reparação." },
};
export const SUPPORT_STATUS: Record<string, { label: string; tone: string }> = {
  auto_resolved: { label: "Resolvido automaticamente", tone: "teal" },
  pending_human: { label: "Na fila humana", tone: "amber" },
  awaiting_customer: { label: "Aguardando cliente", tone: "blue" },
  pending_approval: { label: "Aguardando aprovação", tone: "violet" },
  resolved: { label: "Resolvido", tone: "green" },
  new: { label: "Novo", tone: "gray" },
};
export const SENTIMENT: Record<string, string> = { positivo: "Positivo", neutro: "Neutro", negativo: "Negativo", muito_negativo: "Muito negativo" };

export function ChannelBadge({ channel }: { channel: string }) {
  const c = CHANNEL[channel] || { label: channel, tone: "gray", icon: MessageCircle };
  const Icon = c.icon;
  return <Badge tone={c.tone}><Icon size={11} aria-hidden /> {c.label}</Badge>;
}
export function UrgencyBadge({ urgency }: { urgency?: string | null }) {
  if (!urgency) return null;
  const u = URGENCY[urgency] || { label: urgency, tone: "gray" };
  return <Badge tone={u.tone}>urgência {u.label.toLowerCase()}</Badge>;
}
export function VeracityBadge({ label, score }: { label?: string | null; score?: number | null }) {
  if (!label || label === "nao_aplicavel") return <span className="text-xs text-slate-500">—</span>;
  const v = VERACITY[label];
  return <Badge tone={v.tone}>{v.label}{score !== null && score !== undefined ? ` · ${score}` : ""}</Badge>;
}
export function SupportStatusBadge({ status }: { status: string }) {
  const s = SUPPORT_STATUS[status] || { label: status, tone: "gray" };
  return <Badge tone={s.tone}>{s.label}</Badge>;
}
export function RoutingBadge({ routing }: { routing?: string | null }) {
  if (!routing) return null;
  return routing === "auto" ? <Badge tone="teal">automático</Badge> : <Badge tone="amber">pessoa</Badge>;
}
export const hours = (v: any) => (v === null || v === undefined ? "—" : `${Number(v).toLocaleString("pt-BR", { maximumFractionDigits: 0 })} h`);
export const minutesLabel = (v: any) => {
  if (v === null || v === undefined) return "—";
  const n = Number(v);
  if (n < 90) return `${n.toLocaleString("pt-BR", { maximumFractionDigits: 0 })} min`;
  return `${(n / 60).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} h`;
};
