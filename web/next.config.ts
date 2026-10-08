import type { NextConfig } from "next";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,

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
