import type { NextConfig } from "next";

const apiProxyTarget = process.env.API_PROXY_TARGET;

const nextConfig: NextConfig = {
  images: {
    domains: ["i.scdn.co", "lastfm.freetls.fastly.net"],
  },
  async rewrites() {
    if (!apiProxyTarget) {
      return [];
    }

    return [
      {
        source: "/api/auth/callback",
        destination: `${apiProxyTarget}/auth/callback`,
      },
      {
        source: "/api/auth/lastfm/callback",
        destination: `${apiProxyTarget}/api/auth/lastfm/callback`,
      },
      {
        source: "/api/:path*",
        destination: `${apiProxyTarget}/:path*`,
      },
    ];
  },
};

export default nextConfig;
