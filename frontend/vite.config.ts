import react from "@vitejs/plugin-react";
import { loadEnv } from "vite";
import { defineConfig } from "vitest/config";

export default defineConfig(({ mode }) => {
  // Browsers call /api on this host; only Vite connects to the backend.
  const env = loadEnv(mode, process.cwd(), "DEV_API_TARGET");
  const apiProxy = {
    "/api": {
      target: env.DEV_API_TARGET || "http://127.0.0.1:8000",
      changeOrigin: true,
    },
  };

  return {
    plugins: [react()],
    server: {
      host: "0.0.0.0",
      port: 3000,
      strictPort: true,
      proxy: apiProxy,
    },
    preview: {
      host: "0.0.0.0",
      port: 3000,
      strictPort: true,
      proxy: apiProxy,
    },
    test: {
      environment: "jsdom",
      globals: false,
      setupFiles: ["./src/test/setup.ts"],
      css: false,
    },
  };
});