import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Builds into the Python package so `python -m stitchproof.app.server` serves it with no Node at runtime.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    outDir: "../src/stitchproof/app/web",
    emptyOutDir: true,
    assetsDir: "assets",
  },
  server: {
    host: "127.0.0.1",
    proxy: { "/api": "http://127.0.0.1:7860" },
  },
});
