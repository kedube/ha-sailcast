import { readFileSync } from "node:fs";

import { defineConfig, type Plugin } from "vite";

const WORKER = "maplibre-gl-worker.mjs";

/**
 * MapLibre looks for its worker next to its own code, so the build puts the
 * worker beside the panel's other files. It's only loaded with the spot map.
 */
function maplibreWorker(): Plugin {
  return {
    name: "maplibre-worker",
    apply: "build",
    generateBundle() {
      this.emitFile({
        type: "asset",
        fileName: WORKER,
        source: readFileSync(new URL(`node_modules/maplibre-gl/dist/${WORKER}`, import.meta.url)),
      });
    },
  };
}

// `npm run build` writes the panel module into the integration, where Home
// Assistant serves it, with the map in a chunk of its own that loads when a
// spot editor opens. It's built as an app rather than a library so it's
// minified; paths are relative because Home Assistant serves it from
// /sailcast_static/. `npm run demo` serves index.html with the recorded week.
export default defineConfig(({ command }) => ({
  base: command === "build" ? "./" : "/",
  plugins: [maplibreWorker()],
  build: {
    outDir: "../custom_components/sailcast/frontend",
    emptyOutDir: true,
    target: "es2022",
    modulePreload: false,
    // MapLibre's own chunk is about 1 MB; it only loads with the spot map.
    chunkSizeWarningLimit: 1200,
    rollupOptions: {
      input: "src/sailcast-panel.ts",
      output: {
        format: "es",
        entryFileNames: "sailcast-panel.js",
        chunkFileNames: "[name]-[hash].js",
      },
    },
  },
}));
