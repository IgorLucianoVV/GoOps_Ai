/** @type {import('next').NextConfig} */
// O navegador fala com o próprio Next.js em "/api"; o Next repassa para o backend (proxy).
// Assim frontend e API ficam na MESMA origem: sem CORS e com cookies de sessão funcionando em qualquer porta.
// Aceita "http://host:porta" ou só "host:porta" (formato do hostport da rede privada do Render).
const RAW_API = (process.env.API_INTERNAL_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const API_INTERNAL_URL = RAW_API.includes("://") ? RAW_API : `http://${RAW_API}`;

const nextConfig = {
  reactStrictMode: true,
  output: "standalone",
  eslint: { ignoreDuringBuilds: true },
  poweredByHeader: false,
  // O pipeline completo pode levar mais de 30 s (padrão do proxy): sem isso o navegador recebe 500 com a execução em andamento.
  experimental: { proxyTimeout: 300_000 },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_INTERNAL_URL}/api/:path*` }];
  },
};
export default nextConfig;
