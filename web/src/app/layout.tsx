import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";

import { Providers } from "@/app/providers";
import { ThemeScript } from "@/components/theme-toggle";

import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-sans-var",
});

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: "Bridgga — AI Customer Acquisition OS",
    template: "%s | Bridgga",
  },
  description:
    "Find the companies most likely to need what you sell, reach the right decision makers, and connect every conversation to revenue.",
  openGraph: {
    type: "website",
    siteName: "Bridgga",
    locale: "en",
  },
  robots: { index: true, follow: true },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  // Pinch zoom stays available: capping it fails WCAG 1.4.4.
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#101216" },
  ],
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={inter.variable} suppressHydrationWarning>
      <head>
        <ThemeScript />
      </head>
      {/* Browser extensions -- Grammarly, password managers, translators --
          add their own attributes to <body> before React hydrates, which
          React reports as a mismatch the app cannot fix. The flag applies to
          this element's own attributes only, one level deep, so a genuine
          mismatch anywhere inside the app is still reported. */}
      <body suppressHydrationWarning>
        {/* First stop for keyboard users (PRD section 112). */}
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-accent focus:px-4 focus:py-2 focus:text-accent-fg"
        >
          Skip to content
        </a>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
