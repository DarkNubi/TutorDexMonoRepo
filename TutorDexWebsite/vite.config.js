import { defineConfig } from "vite";
import { resolve } from "node:path";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": resolve(__dirname, "src"),
    },
  },
  define: {
    __BUILD_TIME__: JSON.stringify(new Date().toISOString()),
  },
  build: {
    rollupOptions: {
      input: {
        index: resolve(__dirname, "index.html"),
        assignments: resolve(__dirname, "assignments.html"),
        profile: resolve(__dirname, "profile.html"),
        auth: resolve(__dirname, "auth.html"),
        resetPassword: resolve(__dirname, "reset-password.html"),
        notFound: resolve(__dirname, "404.html"),
      },
    },
  },
});
