/// <reference types="vitest" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const proxy = { "/api": "http://localhost:8000", "/ws": { target: "ws://localhost:8000", ws: true } };

export default defineConfig({
  plugins: [react()],
  server: { proxy },
  preview: { proxy },  // Playwright prüft das fertige Bundle (vite preview) gegen das Backend
  test: { environment: "jsdom", globals: true, exclude: ["e2e/**", "node_modules/**"] },
});
