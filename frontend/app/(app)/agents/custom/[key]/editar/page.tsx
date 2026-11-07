"use client";
import Link from "next/link";
import { Empty, ErrorBox, Loading, PageHeader } from "@/components/ui";
import CustomAgentForm from "@/features/agents/CustomAgentForm";
import { useApi } from "@/hooks/useApi";

export default function EditAgentPage({ params }: { params: { key: string } }) {
  const { data, error, loading, reload } = useApi<any>(`/agents/custom/${params.key}`);
  return (
    <>
      <PageHeader kicker="Agentes de IA" title={data ? `Editar · ${data.name}` : "Editar agente"} />
      <ErrorBox error={error} onRetry={reload} />
      {loading && !data && <Loading />}
      {data && data.template === "llm_task" && <CustomAgentForm agent={data} />}
      {data && data.template !== "llm_task" && <Empty title="Este agente foi criado a partir de um modelo de setor"
        hint="Agentes de modelo (monitor, resumo, causas, tarefa com ação) são configurados na página do setor."
        action={<Link className="btn-primary" href={`/setores/${data.domain}`}>Abrir o setor</Link>} />}
    </>
  );
}
