import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

const here = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  root: here,
  base: "./",
  resolve: { alias: { "@shared": path.resolve(here, "../../shared/js") } },
  server: { fs: { allow: [path.resolve(here, "../..")] } },
  build: { target: "es2020", outDir: "dist", emptyOutDir: true },
});
