"use client";
import { createContext, useCallback, useContext, useEffect, useState } from "react";

export type Theme = "light" | "dark";

/** Paletas de visualização: seguras para daltonismo (base Okabe–Ito), contraste ≥ 3:1 contra o fundo do gráfico
 *  (WCAG 1.4.11). Escala de NPS divergente azul→laranja, sem depender de vermelho/verde. */
export interface ChartPalette {
  grid: string; axis: string; axisLine: string; tooltipBg: string; tooltipBorder: string; text: string; cursor: string;
  primary: string; secondary: string; tertiary: string; muted: string; positive: string; neutral: string; negative: string;
  warning: string; nps_high: string; nps_mid: string; nps_low: string; nps_neg: string; series: string[];
}

export const CHART_PALETTES: Record<Theme, ChartPalette> = {
  light: {
    grid: "#E4E4E0", axis: "#63636B", axisLine: "#D4D4CF", tooltipBg: "#FFFFFF", tooltipBorder: "#D4D4CF", text: "#18181B",
    cursor: "#F1F1EE", primary: "#005BAA", secondary: "#E2583A", tertiary: "#0B7472", muted: "#8B8B93",
    positive: "#0072B2", neutral: "#A1A1AA", negative: "#D55E00", warning: "#B07D00",
    nps_high: "#005BAA", nps_mid: "#5C9BD5", nps_low: "#C98A00", nps_neg: "#D55E00",
    series: ["#005BAA", "#E2583A", "#0B7472", "#B07D00", "#7B5CE0", "#CC79A7", "#63636B"],
  },
  dark: {
    grid: "#2A2A2F", axis: "#A1A1AA", axisLine: "#43434A", tooltipBg: "#1A1A1D", tooltipBorder: "#43434A", text: "#FAFAFA",
    cursor: "#26262B", primary: "#7DB7F2", secondary: "#FF9C83", tertiary: "#5ED6D0", muted: "#6B6B74",
    positive: "#56B4E9", neutral: "#8C8C96", negative: "#F28A3C", warning: "#F7C75C",
    nps_high: "#7DB7F2", nps_mid: "#A9CFF7", nps_low: "#F7C75C", nps_neg: "#F28A3C",
    series: ["#7DB7F2", "#FF9C83", "#5ED6D0", "#F7C75C", "#B9A6FF", "#E59CC4", "#D4D4D8"],
  },
};

interface ThemeState { theme: Theme; toggle: () => void; setTheme: (t: Theme) => void; chart: ChartPalette; }
const ThemeContext = createContext<ThemeState>({ theme: "light", toggle: () => {}, setTheme: () => {}, chart: CHART_PALETTES.light });
const KEY = "goops_theme";

/** Script executado antes da pintura para evitar "flash" de tema incorreto. */
export const themeInitScript = `(function(){try{var t=localStorage.getItem("${KEY}");if(t!=="light"&&t!=="dark"){t=window.matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light"}document.documentElement.setAttribute("data-theme",t)}catch(e){document.documentElement.setAttribute("data-theme","light")}})();`;

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<Theme>("light");
  useEffect(() => {
    const current = document.documentElement.getAttribute("data-theme");
    setThemeState(current === "dark" ? "dark" : "light");
  }, []);
  const setTheme = useCallback((t: Theme) => {
    setThemeState(t);
    document.documentElement.setAttribute("data-theme", t);
    try { window.localStorage.setItem(KEY, t); } catch { /* armazenamento indisponível */ }
  }, []);
  const toggle = useCallback(() => setTheme(theme === "dark" ? "light" : "dark"), [theme, setTheme]);
  return <ThemeContext.Provider value={{ theme, toggle, setTheme, chart: CHART_PALETTES[theme] }}>{children}</ThemeContext.Provider>;
}

export const useTheme = () => useContext(ThemeContext);
