/** @type {import('next').NextConfig} */
const BACKEND = process.env.BACKEND_URL || "http://localhost:8200";

const nextConfig = {
  reactStrictMode: false, // React Flow + strict mode double-invokes drag handlers
  async rewrites() {
    // same-origin proxy so the browser talks to /api/* and Next forwards to FastAPI
    return [
      { source: "/api/:path*", destination: `${BACKEND}/api/:path*` },
      // public webhook triggers for deployed workflows (token is the credential)
      { source: "/hooks/:path*", destination: `${BACKEND}/hooks/:path*` },
    ];
  },
};

module.exports = nextConfig;
