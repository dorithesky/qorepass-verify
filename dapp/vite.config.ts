import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The public REST APIs send no CORS headers, so the browser reaches them
// through the dev (and preview) server: /lcd-testnet and /lcd-mainnet are
// forwarded to each network's REST endpoint (see REST_PROXY in src/App.tsx).
// In production, serve the app behind a proxy that does the same.
const rest = (target: string) => ({
  target,
  changeOrigin: true,
  rewrite: (p: string) => p.replace(/^\/lcd-(testnet|mainnet)/, ""),
});
const proxy = {
  "/lcd-testnet": rest("https://api-testnet.qore.host"),
  "/lcd-mainnet": rest("https://api.qore.host"),
};

export default defineConfig({
  plugins: [react()],
  // Built into the repository's Pages tree, so the app is a URL a judge can
  // open: https://dorithesky.github.io/qorepass-verify/web/dapp/
  base: "/qorepass-verify/web/dapp/",
  build: { outDir: "../web/dapp", emptyOutDir: true },
  server: { port: 5173, proxy },
  preview: { proxy },
});
