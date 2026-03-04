import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/ws": {
        target: "ws://localhost:8000",
        ws: true,
      },
      "/health": { target: "http://localhost:8000" },
      "/trades": { target: "http://localhost:8000" },
      "/account": { target: "http://localhost:8000" },
      "/stats": { target: "http://localhost:8000" },
      "/wallet": { target: "http://localhost:8000" },
    },
  },
});
