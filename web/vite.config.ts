import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In development the app calls /api/..., which is proxied to the Express API
// (api/, port 4000). In production VITE_API_URL points at the deployed API.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.FOOTSTATS_API ?? "http://localhost:4000",
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
