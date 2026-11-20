import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  resolve: { tsconfigPaths: true },
  plugins: [react(), tailwindcss()],
  server: {
    // Allow sharing the dev server through Cloudflare quick tunnels.
    allowedHosts: [".trycloudflare.com"],
    // FastAPI runs on 8000 in dev; the SPA calls /api/* through this proxy.
    proxy: { "/api": "http://localhost:8000" },
  },
});
