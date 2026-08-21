import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The backend CORS allowlist contains http://localhost:3000, so the dev server
// runs there instead of Vite's default 5173. strictPort makes a port clash fail
// loudly rather than silently moving to an origin the backend would reject.
export default defineConfig({
  plugins: [react()],
  server: {
    host: "localhost",
    port: 3000,
    strictPort: true,
  },
  preview: {
    port: 3000,
    strictPort: true,
  },
  test: {
    environment: "jsdom",
    globals: false,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
