import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

const here = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  clearScreen: false,
  resolve: { alias: { "@shared": path.resolve(here, "../shared/js") } },
  server: { port: 1420, strictPort: true, fs: { allow: [".."] } },
  build: { target: "es2021", outDir: "dist" },
});
