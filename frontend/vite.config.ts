/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:8765", changeOrigin: true },
      "/ws": {
        target: "ws://localhost:8765",
        ws: true,
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/ws/, "/api/analysis/ws"),
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
  },
});
