import type { NextConfig } from "next";

const apiProxyTarget = process.env.API_PROXY_TARGET;

const nextConfig: NextConfig = {
  images: {
    domains: ["i.scdn.co"],
  },
  async rewrites() {
    if (!apiProxyTarget) {
      return [];
    }

    return [
      {
        source: "/api/auth/callback",
        destination: `${apiProxyTarget}/api/auth/callback`,
      },
      {
        source: "/api/:path*",
        destination: `${apiProxyTarget}/:path*`,
      },
    ];
  },
};

export default nextConfig;
