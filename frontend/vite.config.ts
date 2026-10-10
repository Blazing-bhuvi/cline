import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The backend runs on port 8000; proxy API calls during development.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
