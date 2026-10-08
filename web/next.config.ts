import type { NextConfig } from "next";

// Where the Next server forwards /api and /auth-api. Server-side only, and so
// deliberately not a NEXT_PUBLIC_ variable: in a container this is an internal
// hostname like http://backend:8000, which the browser cannot resolve and
// which has no business being inlined into a client bundle.
const API_URL =
  process.env.API_PROXY_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,

  // Traces the modules actually reached and emits them next to a server into
  // .next/standalone, which is all the production container ships. Harmless
  // outside Docker: `next dev` and `next start` ignore it.
  output: "standalone",

  // Note: Next normalises a trailing slash away before applying a rewrite, so
  // the proxied API routes are declared without one on the Django side (see
  // backend/apps/api/v1/urls.py). Leaving the default redirect enabled means a
  // stray /api/v1/me/ still resolves via one 308 rather than 404ing.

  // The marketing site is SEO-critical (PRD section 19), so keep images
  // optimised and let Next emit modern formats.
  images: { formats: ["image/avif", "image/webp"] },

  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "X-Frame-Options", value: "DENY" },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=()",
          },
        ],
      },
    ];
  },

  async rewrites() {
    // Same-origin proxy to Django. Keeping the API same-origin means the
    // session cookie stays SameSite=Lax and CSRF works without relaxing
    // cookie policy for a cross-site setup.
    return [
      { source: "/api/:path*", destination: `${API_URL}/api/:path*` },
      { source: "/auth-api/:path*", destination: `${API_URL}/auth/:path*` },
    ];
  },
};

export default nextConfig;
