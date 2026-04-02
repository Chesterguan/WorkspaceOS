import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Required for the Docker multi-stage build: produces a self-contained
  // .next/standalone directory that can run without node_modules.
  output: "standalone",
};

export default nextConfig;
