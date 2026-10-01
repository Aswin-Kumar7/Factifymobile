import type { NextConfig } from "next";

const api = (process.env.FACTIFY_API_INTERNAL || "http://localhost:8000").replace(/\/$/, "");

const nextConfig: NextConfig = {
  // A small self-contained server for the Docker image (web/Dockerfile).
  output: "standalone",
  poweredByHeader: false,
  // On the server Caddy sends /v1 straight to the API; locally, this does.
  async rewrites() {
    return [{ source: "/v1/:path*", destination: `${api}/v1/:path*` }];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "X-Frame-Options", value: "DENY" },
        ],
      },
    ];
  },
};

export default nextConfig;
