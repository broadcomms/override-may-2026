import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

// Per docs/04-api.md §11: the Next.js / Vite app proxies /api/* to FastAPI.
// In dev that's the local uvicorn on :8000.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
      // Reach the captured demo fixture directly — fixture-first dev pattern
      "@fixtures": path.resolve(__dirname, "..", "tests", "fixtures"),
    },
  },
  server: {
    port: 3000,
    strictPort: true,
    proxy: {
      "/api": {
        target: process.env.VITE_API_TARGET || "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
    rollupOptions: {
      output: {
        // Split recharts (and its d3 transitive deps) into a separate chunk —
        // the energy curve is below-the-fold on /upload, so this helps cold-load.
        manualChunks: {
          recharts: ["recharts"],
          "react-vendor": ["react", "react-dom", "react-router-dom"],
        },
      },
    },
  },
});
