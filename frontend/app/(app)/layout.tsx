"use client";
import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import CommandPalette from "@/components/CommandPalette";
import Sidebar from "@/components/Sidebar";
import Topbar from "@/components/Topbar";
import { Loading } from "@/components/ui";
import { useAuth } from "@/hooks/useAuth";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [menu, setMenu] = useState(false);
  const [palette, setPalette] = useState(false);
  useEffect(() => { if (!loading && !user) router.replace("/login"); }, [loading, user, router]);
  useEffect(() => { setMenu(false); }, [pathname]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setPalette((p) => !p); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  if (loading || !user) return <div className="grid h-screen place-items-center"><Loading label="Verificando sessão…" /></div>;
  return (
    <div className="flex h-screen overflow-hidden">
      <a href="#conteudo" className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-[90] focus:rounded focus:bg-brand-600 focus:px-3 focus:py-2 focus:text-[#FFFFFF]">Pular para o conteúdo</a>
      <div className={menu ? "fixed inset-0 z-40 lg:static lg:z-auto" : "hidden lg:block"}>
        {menu && <button aria-label="Fechar menu" className="absolute inset-0 bg-black/50 lg:hidden" onClick={() => setMenu(false)} />}
        <div className="relative h-full"><Sidebar /></div>
      </div>
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <Topbar onMenu={() => setMenu(true)} onSearch={() => setPalette(true)} />
        <main id="conteudo" className="flex-1 overflow-y-auto" tabIndex={-1}>
          <div className="mx-auto max-w-[1400px] px-4 py-6 sm:px-8 sm:py-8">{children}</div>
        </main>
      </div>
      <CommandPalette open={palette} onClose={() => setPalette(false)} />
    </div>
  );
}
