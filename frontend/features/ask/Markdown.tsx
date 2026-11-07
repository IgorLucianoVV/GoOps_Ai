"use client";
/** Renderizador mínimo e SEGURO (sem HTML bruto): parágrafos, listas "- ", **negrito**, _itálico_ e `código`. */
function inline(text: string, key: string): React.ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*|_[^_]+_|`[^`]+`)/g);
  return parts.filter(Boolean).map((p, i) => {
    if (p.startsWith("**") && p.endsWith("**")) return <strong key={`${key}-${i}`} className="font-semibold text-white">{p.slice(2, -2)}</strong>;
    if (p.startsWith("`") && p.endsWith("`")) return <code key={`${key}-${i}`} className="rounded bg-ink-800 px-1 text-[0.9em]">{p.slice(1, -1)}</code>;
    if (p.startsWith("_") && p.endsWith("_") && p.length > 2) return <em key={`${key}-${i}`} className="text-slate-400">{p.slice(1, -1)}</em>;
    return <span key={`${key}-${i}`}>{p}</span>;
  });
}

export default function Markdown({ text }: { text: string }) {
  const lines = (text || "").split("\n");
  const blocks: React.ReactNode[] = [];
  let list: string[] = [];
  const flush = (k: number) => {
    if (list.length) {
      blocks.push(<ul key={`ul-${k}`} className="my-1 list-disc space-y-0.5 pl-5">{list.map((li, i) => <li key={i}>{inline(li, `li-${k}-${i}`)}</li>)}</ul>);
      list = [];
    }
  };
  lines.forEach((raw, i) => {
    const line = raw.trimEnd();
    const m = line.match(/^\s*(?:[-*•]|\d+\.)\s+(.*)$/);
    if (m) { list.push(m[1]); return; }
    flush(i);
    if (!line.trim()) return;
    const h = line.match(/^#{1,4}\s+(.*)$/);
    blocks.push(h ? <p key={i} className="mt-2 font-semibold text-white">{inline(h[1], `h-${i}`)}</p> : <p key={i} className="my-1">{inline(line, `p-${i}`)}</p>);
  });
  flush(lines.length);
  return <div className="text-sm leading-relaxed text-slate-200">{blocks}</div>;
}
