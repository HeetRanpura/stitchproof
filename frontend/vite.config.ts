import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

declare const process: { env: Record<string, string | undefined> };

// Builds into the Python package so `python -m stitchproof.app.server` serves it with no Node at runtime.
// On Vercel (VERCEL=1 during builds) the frontend is its own service, so it builds to frontend/dist.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    outDir: process.env.VERCEL ? "dist" : "../src/stitchproof/app/web",
    emptyOutDir: true,
    assetsDir: "assets",
  },
  server: {
    host: "127.0.0.1",
    proxy: { "/api": "http://127.0.0.1:7860" },
  },
});
