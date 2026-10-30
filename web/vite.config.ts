/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The web UI runs on 127.0.0.1:5175 and talks to the API on 127.0.0.1:8200 through a proxy,
// so the browser sees one origin and the API needs no CORS settings.
export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5175,
    strictPort: true,
    proxy: { "/api": "http://127.0.0.1:8200" },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/setupTests.ts"],
  },
});
