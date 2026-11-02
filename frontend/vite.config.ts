import { defineConfig } from "vite";

// `npm run build` writes the panel module into the integration, where Home
// Assistant serves it. `npm run demo` serves index.html with made-up data.
export default defineConfig({
  build: {
    lib: {
      entry: "src/sailcast-panel.ts",
      formats: ["es"],
      fileName: () => "sailcast-panel.js",
    },
    outDir: "../custom_components/sailcast/frontend",
    emptyOutDir: true,
    target: "es2022",
  },
});
