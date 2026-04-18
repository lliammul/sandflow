import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "export",
  reactCompiler: false,
  turbopack: {
    root: __dirname,
  },
};

export default nextConfig;
