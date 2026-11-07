"""Grafo LangGraph do “Pergunte ao GoOps”.

    START → agent ──(pediu ferramentas?)──► tools ──► agent … ──(resposta final)──► END

* agent: o modelo escolhido (qualquer provedor) com as ferramentas governadas vinculadas (bind_tools).
* tools: executa SOMENTE ferramentas do Toolbox, com as permissões de quem pergunta; erros viram ToolMessage(status=error).
* Limite de etapas (MAX_STEPS) e de custo verificados a cada passagem pelo nó agent.
"""
import json
import time
from typing import Annotated, Any, Callable, Dict, List, Optional, Tuple, TypedDict

from goops_core.errors import GoOpsError, PermissionDenied, ValidationError
from goops_core.util import to_jsonable

from .providers import message_text, usage_of

MAX_STEPS = 6


def _strip_keys(schema: Any, keys: Tuple[str, ...]) -> Any:
    if isinstance(schema, dict):
        return {k: _strip_keys(v, keys) for k, v in schema.items() if k not in keys}
    if isinstance(schema, list):
        return [_strip_keys(v, keys) for v in schema]
    return schema


def run_assistant_graph(chat_model: Any, tool_specs: List[Dict[str, Any]], execute: Callable[[str, Dict[str, Any]], Any],
                        system_prompt: str, history: List[Dict[str, str]], question: str,
                        on_llm_call: Callable[[Dict[str, Any]], None],
                        budget_ok: Callable[[], bool], provider: str = "") -> Tuple[str, Dict[str, Any]]:
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
    from langgraph.graph import END, START, StateGraph
    from langgraph.graph.message import add_messages

    class State(TypedDict):
        messages: Annotated[list, add_messages]
        steps: int

    # Gemini não aceita "additionalProperties" em declarações de função
    strip = ("additionalProperties",) if provider == "google" else ()
    openai_tools = [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                                      "parameters": _strip_keys(t["parameters"], strip)}} for t in tool_specs]
    bound = chat_model.bind_tools(openai_tools)

    def agent(state: State) -> Dict[str, Any]:
        if state["steps"] >= MAX_STEPS:
            raise ValidationError("Limite de etapas de raciocínio atingido")
        if not budget_ok():
            raise ValidationError("Limite de custo por execução atingido")
        t0 = time.perf_counter()
        msg = bound.invoke([SystemMessage(content=system_prompt)] + list(state["messages"]))
        on_llm_call({**usage_of(msg), "latency_ms": int((time.perf_counter() - t0) * 1000)})
        return {"messages": [msg], "steps": state["steps"] + 1}

    def tools(state: State) -> Dict[str, Any]:
        last = state["messages"][-1]
        out = []
        for call in getattr(last, "tool_calls", None) or []:
            try:
                result = execute(call["name"], call.get("args") or {})
                content, status = json.dumps(to_jsonable(result), ensure_ascii=False)[:12000], "success"
            except PermissionDenied as exc:
                content, status = json.dumps({"erro": f"Sem permissão: {exc.message}"}, ensure_ascii=False), "error"
            except GoOpsError as exc:
                content, status = json.dumps({"erro": exc.message}, ensure_ascii=False), "error"
            out.append(ToolMessage(content=content, tool_call_id=call["id"], name=call["name"], status=status))
        return {"messages": out}

    def route(state: State) -> str:
        last = state["messages"][-1]
        return "tools" if getattr(last, "tool_calls", None) else END

    graph = StateGraph(State)
    graph.add_node("agent", agent)
    graph.add_node("tools", tools)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", route, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")
    app = graph.compile()

    msgs: List[Any] = [HumanMessage(content=h["content"]) if h["role"] == "user" else AIMessage(content=h["content"])
                       for h in history]
    msgs.append(HumanMessage(content=question))
    final = app.invoke({"messages": msgs, "steps": 0}, config={"recursion_limit": 2 * MAX_STEPS + 4})
    last = final["messages"][-1]
    return message_text(last).strip(), {"steps": final["steps"], "nodes": ["agent", "tools"]}


def complete_text(chat_model: Any, system_prompt: str, prompt: str) -> Tuple[str, Dict[str, Any], int]:
    """Uma chamada simples (narrativas/resumos) via LangChain."""
    from langchain_core.messages import HumanMessage, SystemMessage
    t0 = time.perf_counter()
    msg = chat_model.invoke([SystemMessage(content=system_prompt), HumanMessage(content=prompt)])
    return message_text(msg), usage_of(msg), int((time.perf_counter() - t0) * 1000)
