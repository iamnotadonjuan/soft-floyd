import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

// Dev server proxies API and MCP calls to the FastMCP/FastAPI backend
// started by `make dev-server` (uv run soft-floyd serve), so the web app
// never hardcodes localhost:8000 in its own fetch calls.
export default defineConfig(({ mode }) => {
  const target = loadEnv(mode, ".", "SOFT_FLOYD_").SOFT_FLOYD_DEV_API_TARGET || "http://127.0.0.1:8000";
  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: { "/api": target, "/mcp": target },
    },
  };
});
