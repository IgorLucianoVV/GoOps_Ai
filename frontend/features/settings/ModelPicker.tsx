"use client";
import { useEffect, useState } from "react";

export interface ModelOption { id: string; label: string }

const CUSTOM = "__custom__";

/** Lista de seleção de modelos do provedor escolhido + opção "Outro…" para digitar um id livre. */
export default function ModelPicker({ value, options, onChange, disabled, ariaLabel = "Modelo", className = "" }: {
  value: string; options: ModelOption[]; onChange: (id: string, label?: string) => void;
  disabled?: boolean; ariaLabel?: string; className?: string;
}) {
  const known = options.some((o) => o.id === value);
  const [custom, setCustom] = useState(!known && !!value);
  useEffect(() => { if (options.some((o) => o.id === value)) setCustom(false); else if (value) setCustom(true); }, [value, options]);
  const showInput = custom || options.length === 0;
  return (
    <div className={`flex min-w-0 gap-2 ${className}`}>
      <select aria-label={ariaLabel} className="input min-w-0 flex-1" disabled={disabled}
        value={showInput ? CUSTOM : value}
        onChange={(e) => {
          if (e.target.value === CUSTOM) { setCustom(true); onChange(""); return; }
          setCustom(false);
          const opt = options.find((o) => o.id === e.target.value);
          onChange(e.target.value, opt?.label);
        }}>
        {!value && !showInput && <option value="">Selecione…</option>}
        {options.map((o) => <option key={o.id} value={o.id}>{o.label === o.id ? o.id : `${o.label} · ${o.id}`}</option>)}
        <option value={CUSTOM}>Outro (digitar id)…</option>
      </select>
      {showInput && <input aria-label={`${ariaLabel} (id)`} className="input min-w-0 flex-1 font-mono" placeholder="id exato do modelo"
        disabled={disabled} value={value} onChange={(e) => onChange(e.target.value)} />}
    </div>
  );
}
