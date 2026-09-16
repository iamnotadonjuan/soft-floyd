import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Dev server proxies API and MCP calls to the FastMCP/FastAPI backend
// started by `make dev-server` (uv run soft-floyd serve), so the web app
// never hardcodes localhost:8000 in its own fetch calls.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/mcp": "http://127.0.0.1:8000",
    },
  },
});
