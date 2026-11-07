import type { Metadata, Viewport } from "next";
import "@/styles/globals.css";
import { AuthProvider } from "@/hooks/useAuth";
import { ConfirmProvider } from "@/hooks/useConfirm";
import { ThemeProvider, themeInitScript } from "@/hooks/useTheme";
import { ToastProvider } from "@/hooks/useToast";

export const metadata: Metadata = {
  title: "GoOps AI — Operational Intelligence",
  description: "Plataforma de inteligência operacional com Lakehouse de dados governado e agentes de IA supervisionados.",
};
export const viewport: Viewport = { themeColor: "#F6F6F3", width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR" suppressHydrationWarning>
      <head><script dangerouslySetInnerHTML={{ __html: themeInitScript }} /></head>
      <body>
        <ThemeProvider>
          <ToastProvider>
            <ConfirmProvider>
              <AuthProvider>{children}</AuthProvider>
            </ConfirmProvider>
          </ToastProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
