import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development, /api is proxied to the FastAPI server on port 8000.
// Set FOOTSTATS_API to point at a backend running somewhere else.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { "/api": process.env.FOOTSTATS_API ?? "http://localhost:8000" },
  },
});
