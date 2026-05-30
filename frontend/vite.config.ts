import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const base = env.VITE_BASE || "/";
  const outDir = env.VITE_OUT_DIR || "../web/dist";

  return {
    base,
    plugins: [react()],
    build: {
      outDir,
      emptyOutDir: true,
    },
    server: {
      port: 5173,
      proxy: {
        "/api": "http://127.0.0.1:8080",
      },
    },
  };
});
