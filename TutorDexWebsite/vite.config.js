import { defineConfig } from "vite";
import { resolve } from "node:path";

export default defineConfig({
  define: {
    __BUILD_TIME__: JSON.stringify(new Date().toISOString()),
  },
  build: {
    rollupOptions: {
      input: {
        index: resolve(__dirname, "index.html"),
        assignments: resolve(__dirname, "assignments.html"),
        profile: resolve(__dirname, "profile.html"),
        notFound: resolve(__dirname, "404.html"),
      },
    },
  },
});
