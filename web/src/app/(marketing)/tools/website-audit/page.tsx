import type { Metadata } from "next";

import { WebsiteAuditTool } from "@/components/marketing/website-audit-tool";

/**
 * The website sales audit, as a free tool (PRD sections 17 and 49).
 *
 * Public, in the marketing route group, and it asks for nothing. Section 17
 * says "useful free result, optional signup" in that order: the result is
 * shown in full before anything is requested, because a tool that holds the
 * answer hostage is an ad with a text field.
 *
 * The structured data is the point as much as the copy. This page is meant to
 * be found by somebody searching "is my website converting", and an answer
 * engine can only quote what it can parse (section 20).
 */

const TITLE = "Free website sales audit";
const DESCRIPTION =
  "Paste a URL and see what your homepage tells a buyer: value proposition, " +
  "ICP clarity, calls to action, trust, pricing clarity, SEO and AEO readiness — " +
  "with the specific fix for everything it finds.";

export const metadata: Metadata = {
  title: TITLE,
  description: DESCRIPTION,
  alternates: { canonical: "/tools/website-audit" },
  openGraph: {
    title: `${TITLE} — Bridgga`,
    description: DESCRIPTION,
    url: "/tools/website-audit",
    type: "website",
  },
};

const STRUCTURED_DATA = {
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "WebApplication",
      name: TITLE,
      description: DESCRIPTION,
      applicationCategory: "BusinessApplication",
      operatingSystem: "Any",
      offers: { "@type": "Offer", price: "0", priceCurrency: "USD" },
    },
    {
      "@type": "FAQPage",
      mainEntity: [
        {
          "@type": "Question",
          name: "What does the website sales audit check?",
          acceptedAnswer: {
            "@type": "Answer",
            text:
              "Eight things: whether the value proposition is clear, whether it is " +
              "obvious who the page is for, whether it leads to an action, the calls " +
              "to action themselves, trust markers, pricing clarity, SEO basics and " +
              "readiness for answer engines. Five of the eight are counted directly " +
              "from the HTML rather than judged, so you can check every finding yourself.",
          },
        },
        {
          "@type": "Question",
          name: "Do I need an account?",
          acceptedAnswer: {
            "@type": "Answer",
            text: "No. Paste a URL and the full result is shown immediately.",
          },
        },
        {
          "@type": "Question",
          name: "How long does an audit take?",
          acceptedAnswer: {
            "@type": "Answer",
            text:
              "A few seconds. The page is fetched once, measured, and the three " +
              "judgement-based scores are produced by a language model that is shown " +
              "the measurements so it cannot contradict them.",
          },
        },
      ],
    },
  ],
};

export default function WebsiteAuditPage() {
  return (
    <>
      <script
        type="application/ld+json"
        // Next escapes this for us; the content is a constant defined above,
        // never user input.
        dangerouslySetInnerHTML={{ __html: JSON.stringify(STRUCTURED_DATA) }}
      />
      <WebsiteAuditTool />
    </>
  );
}
