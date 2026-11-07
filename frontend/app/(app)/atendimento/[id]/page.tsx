"use client";
import { useParams, useRouter } from "next/navigation";
import { useEffect } from "react";
import { ErrorBox, Loading } from "@/components/ui";
import { useApi } from "@/hooks/useApi";

/** Links antigos de atendimento abrem a conversa na caixa unificada, com o atendimento selecionado. */
export default function CaseRedirect() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { data, error, reload } = useApi<any>(`/support/contacts/${id}`);
  useEffect(() => { if (data?.conversation_id) router.replace(`/atendimento/caixa?c=${data.conversation_id}&k=${id}`); }, [data, id, router]);
  return error ? <ErrorBox error={error} onRetry={reload} /> : <Loading label="Abrindo conversa…" />;
}
