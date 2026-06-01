import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  typedRoutes: true,
  transpilePackages: ["@changjuan/clients", "@changjuan/shared-types"],
};

export default nextConfig;
