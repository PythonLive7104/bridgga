import type { Metadata } from "next";

import { Hero } from "@/components/marketing/hero";
import { PipelineWalkthrough } from "@/components/marketing/pipeline-walkthrough";
import {
  AfricaSection,
  AgentSection,
  EvidenceSection,
  FaqSection,
  FinalCtaSection,
  IntegrationsSection,
  OutreachSection,
  ProblemSection,
  RevenueSection,
  ThreeQuestionsSection,
} from "@/components/marketing/sections";

export const metadata: Metadata = {
  title: "Turn your website into a customer acquisition engine",
  description:
    "Palatial finds the companies most likely to need your product, identifies the right decision makers, starts relevant conversations, and connects every conversation to revenue.",
  alternates: { canonical: "/" },
  openGraph: {
    title: "Palatial — turn your website into a customer acquisition engine",
    description:
      "AI finds the companies most likely to need your product, identifies the right decision makers, and connects every conversation to revenue. Built for African businesses.",
    url: "/",
    type: "website",
  },
};

/**
 * Homepage.
 *
 * Section order follows PRD section 12. This file is composition only -- each
 * section owns its own content and layout, so reordering the page is a matter
 * of moving one line rather than untangling markup.
 */
export default function HomePage() {
  return (
    <>
      <Hero />
      <ProblemSection />
      <ThreeQuestionsSection />
      <PipelineWalkthrough />
      <EvidenceSection />
      <OutreachSection />
      <AgentSection />
      <RevenueSection />
      <AfricaSection />
      <IntegrationsSection />
      <FaqSection />
      <FinalCtaSection />
    </>
  );
}
