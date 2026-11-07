import type { Config } from "tailwindcss";

/** Cores semânticas via variáveis CSS (tema claro/escuro em styles/globals.css). */
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./features/**/*.{ts,tsx}", "./hooks/**/*.{ts,tsx}"],
  darkMode: ["class", '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        ink: { "950": "rgb(var(--c-ink-950) / <alpha-value>)", "900": "rgb(var(--c-ink-900) / <alpha-value>)", "850": "rgb(var(--c-ink-850) / <alpha-value>)", "800": "rgb(var(--c-ink-800) / <alpha-value>)", "700": "rgb(var(--c-ink-700) / <alpha-value>)", "600": "rgb(var(--c-ink-600) / <alpha-value>)" },
        white: "rgb(var(--c-white) / <alpha-value>)",
        slate: { "100": "rgb(var(--c-slate-100) / <alpha-value>)", "200": "rgb(var(--c-slate-200) / <alpha-value>)", "300": "rgb(var(--c-slate-300) / <alpha-value>)", "400": "rgb(var(--c-slate-400) / <alpha-value>)", "500": "rgb(var(--c-slate-500) / <alpha-value>)", "600": "rgb(var(--c-slate-600) / <alpha-value>)", "700": "rgb(var(--c-slate-700) / <alpha-value>)" },
        brand: { "300": "rgb(var(--c-brand-300) / <alpha-value>)", "400": "rgb(var(--c-brand-400) / <alpha-value>)", "500": "rgb(var(--c-brand-500) / <alpha-value>)", "600": "rgb(var(--c-brand-600) / <alpha-value>)", "700": "rgb(var(--c-brand-700) / <alpha-value>)" },
        emerald: { "200": "rgb(var(--c-emerald-200) / <alpha-value>)", "300": "rgb(var(--c-emerald-300) / <alpha-value>)", "500": "rgb(var(--c-emerald-500) / <alpha-value>)", "700": "rgb(var(--c-emerald-700) / <alpha-value>)", "950": "rgb(var(--c-emerald-950) / <alpha-value>)" },
        rose: { "200": "rgb(var(--c-rose-200) / <alpha-value>)", "300": "rgb(var(--c-rose-300) / <alpha-value>)", "500": "rgb(var(--c-rose-500) / <alpha-value>)", "700": "rgb(var(--c-rose-700) / <alpha-value>)", "950": "rgb(var(--c-rose-950) / <alpha-value>)" },
        amber: { "200": "rgb(var(--c-amber-200) / <alpha-value>)", "300": "rgb(var(--c-amber-300) / <alpha-value>)", "500": "rgb(var(--c-amber-500) / <alpha-value>)", "600": "rgb(var(--c-amber-600) / <alpha-value>)", "950": "rgb(var(--c-amber-950) / <alpha-value>)" },
        sky: { "300": "rgb(var(--c-sky-300) / <alpha-value>)", "500": "rgb(var(--c-sky-500) / <alpha-value>)" },
        violet: { "300": "rgb(var(--c-violet-300) / <alpha-value>)", "500": "rgb(var(--c-violet-500) / <alpha-value>)" },
        teal: { "300": "rgb(var(--c-teal-300) / <alpha-value>)", "500": "rgb(var(--c-teal-500) / <alpha-value>)" },
        navy: { "950": "rgb(var(--c-navy-950) / <alpha-value>)", "900": "rgb(var(--c-navy-900) / <alpha-value>)", "800": "rgb(var(--c-navy-800) / <alpha-value>)", "700": "rgb(var(--c-navy-700) / <alpha-value>)", "600": "rgb(var(--c-navy-600) / <alpha-value>)" },
        coral: { "300": "rgb(var(--c-coral-300) / <alpha-value>)", "400": "rgb(var(--c-coral-400) / <alpha-value>)", "500": "rgb(var(--c-coral-500) / <alpha-value>)" },
        peach: { "400": "rgb(var(--c-peach-400) / <alpha-value>)" },
        accent: { "300": "rgb(var(--c-accent-300) / <alpha-value>)", "400": "rgb(var(--c-accent-400) / <alpha-value>)", "500": "rgb(var(--c-accent-500) / <alpha-value>)" },
      },
      fontFamily: { sans: ["Inter", "ui-sans-serif", "system-ui", "Segoe UI", "Roboto", "Helvetica Neue", "Arial", "sans-serif"] },
      borderRadius: { xl: "var(--radius)" },
    },
  },
  plugins: [],
};
export default config;
