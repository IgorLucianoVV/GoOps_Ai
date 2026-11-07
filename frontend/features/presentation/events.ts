"use client";
import { useEffect } from "react";

/** Eventos do modo apresentação. As páginas só ESCUTAM: o tour nunca mexe no estado interno delas diretamente.
 *  - goops:tour    → { tab }  pede para a página abrir uma aba (ex.: "veracidade", "decides")
 *  - goops:refresh → recarrega os dados das telas abertas (usado depois de uma ação do tour) */
export const TOUR_EVENT = "goops:tour";
export const REFRESH_EVENT = "goops:refresh";

export function emitTourTab(tab: string) {
  if (typeof window !== "undefined") window.dispatchEvent(new CustomEvent(TOUR_EVENT, { detail: { tab } }));
}

export function emitRefresh() {
  if (typeof window !== "undefined") window.dispatchEvent(new Event(REFRESH_EVENT));
}

/** Liga as abas de uma página ao tour: se a aba pedida existir, ela é aberta. */
export function useTourTab(setTab: (t: string) => void, allowed: string[]) {
  const key = allowed.join("|");
  useEffect(() => {
    const on = (e: Event) => {
      const tab = (e as CustomEvent).detail?.tab;
      if (tab && key.split("|").includes(tab)) setTab(tab);
    };
    window.addEventListener(TOUR_EVENT, on);
    return () => window.removeEventListener(TOUR_EVENT, on);
  }, [setTab, key]);
}
