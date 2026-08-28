import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true,
    // Docker Desktop on Windows/macOS bind-mounts don't propagate native
    // filesystem events (inotify) from the host into the Linux container,
    // so chokidar's default watcher silently never fires and the dev server
    // keeps serving a stale bundle after host-side edits. Polling works
    // around it at the cost of a small CPU overhead.
    watch: {
      usePolling: true,
      interval: 300,
    },
  },
});
