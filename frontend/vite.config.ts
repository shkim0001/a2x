import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: {
    port: 5173,
    // 개발 중에는 /api 요청을 FastAPI(8000)로 넘겨 CORS 없이 호출한다.
    proxy: { "/api": "http://localhost:8000" },
  },
});
