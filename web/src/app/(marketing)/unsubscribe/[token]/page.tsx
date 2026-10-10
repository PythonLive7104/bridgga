import type { Metadata } from "next";

import { UnsubscribeForm } from "@/components/marketing/unsubscribe-form";

/**
 * The opt-out landing page (PRD sections 62 and 63).
 *
 * Reached from an email client by somebody who is not signed in and may be
 * annoyed. Everything about it is shaped by that:
 *
 * **One button, above everything else.** No login, no "are you sure", no
 * survey standing between the person and the thing they asked for. The reason
 * box is optional and sits after the confirmation, because feedback that
 * costs somebody their opt-out is not feedback.
 *
 * **`noindex`.** These URLs carry a signed token naming an address. They are
 * not pages, they are instructions, and search engines have no business in
 * them.
 */

export const metadata: Metadata = {
  title: "Unsubscribe",
  robots: { index: false, follow: false },
};

export default async function UnsubscribePage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;
  return <UnsubscribeForm token={token} />;
}
