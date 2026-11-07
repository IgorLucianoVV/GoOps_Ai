/** @type {import('next').NextConfig} */
// O navegador fala com o próprio Next.js em "/api"; o Next repassa para o backend (proxy).
// Assim frontend e API ficam na MESMA origem: sem CORS e com cookies de sessão funcionando em qualquer porta.
const API_INTERNAL_URL = (process.env.API_INTERNAL_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

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
