"use client";
import { PageHeader } from "@/components/ui";
import CustomAgentForm from "@/features/agents/CustomAgentForm";

export default function NewAgentPage() {
  return (
    <>
      <PageHeader kicker="Agentes de IA" title="Novo agente"
        subtitle="Descreva a missão em texto, escolha as ferramentas governadas que ele pode consultar e o que fazer com o resultado. O agente lê dados, escreve relatórios e pode sinalizar alertas — nunca aprova nem executa ações." />
      <CustomAgentForm />
    </>
  );
}
