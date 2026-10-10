"use client";

import { ArrowRight } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";

import { Wordmark } from "@/components/brand";
import { CreateOrganizationStep } from "@/components/onboarding/create-organization";
import { OnboardingProgress } from "@/components/onboarding/progress";
import {
  AnalysisStep,
  ConfirmStep,
  IcpStep,
  MarketsStep,
} from "@/components/onboarding/steps";
import { Button } from "@/components/ui/button";
import { useOnboarding } from "@/lib/hooks/use-onboarding";
import { useSession } from "@/lib/hooks/use-session";

/**
 * The onboarding wizard (PRD section 25, steps 1-5).
 *
 * Steps 6 to 9 — channels, prospects, campaign, launch — arrive with Phase 3.
 *
 * **The server decides where the customer is.** It derives it from the actual
 * records rather than a stored counter, so this page cannot show a tick for
 * something that is not set up, and someone who comes back a week later lands
 * exactly where they stopped. See `apps/organizations/onboarding.py`.
 *
 * **Skipping is local, finishing is not.** A skip moves this session past a
 * step without claiming it was done — the rail still shows it unfinished and
 * the dashboard will still offer it. Only pressing finish records that the
 * customer has been through the path, because that is the one part that is a
 * decision rather than a derivation.
 *
 * Every step is also a real page in the product (`/company-profile`, `/icp`,
 * `/markets`), so nothing here is a one-time screen whose work is lost if
 * somebody closes the tab.
 */

export default function OnboardingPage() {
  const router = useRouter();
  const { me, isLoading } = useSession();
  const hasOrganization = Boolean(me && me.memberships.length > 0);

  const { state, refresh, finish } = useOnboarding({ enabled: hasOrganization });
  const [skipped, setSkipped] = React.useState<string[]>([]);

  // Somebody who has already been through does not get sent round again.
  React.useEffect(() => {
    if (state?.completed_at) router.replace("/dashboard");
  }, [state?.completed_at, router]);

  if (isLoading) {
    return <div className="p-10 text-sm text-fg-subtle">Loading…</div>;
  }

  async function leave() {
    await finish.mutateAsync();
    router.replace("/dashboard");
  }

  const skip = (key: string) => setSkipped((current) => [...current, key]);

  // The first step that is neither finished nor skipped in this session.
  const stepsLeft = (state?.steps ?? []).filter(
    (step) => step.state !== "done" && !skipped.includes(step.key),
  );
  const current = stepsLeft[0]?.key ?? null;

  return (
    <div className="mx-auto min-h-dvh max-w-5xl px-6 py-12">
      <Wordmark height={28} priority className="mb-10" />

      <div className="grid gap-10 lg:grid-cols-[14rem_minmax(0,1fr)]">
        <aside>
          {state ? (
            <OnboardingProgress steps={state.steps} current={current ?? state.current} />
          ) : (
            <p className="text-xs font-medium uppercase tracking-[0.12em] text-accent">
              Step 1 of 5
            </p>
          )}
          {hasOrganization ? (
            <Button variant="ghost" size="sm" className="mt-6" onClick={leave}>
              Skip setup
            </Button>
          ) : null}
        </aside>

        <main className="min-w-0">
          {!hasOrganization ? (
            <CreateOrganizationStep onCreated={refresh} />
          ) : current === "analysis" ? (
            <AnalysisStep onSkip={() => skip("analysis")} />
          ) : current === "confirm" ? (
            <ConfirmStep onSkip={() => skip("confirm")} />
          ) : current === "icp" ? (
            <IcpStep onSkip={() => skip("icp")} />
          ) : current === "markets" ? (
            <MarketsStep onFinish={leave} />
          ) : (
            <div className="space-y-4">
              <h1 className="text-2xl font-semibold tracking-tight text-fg">
                That is the setup done
              </h1>
              <p className="text-sm text-fg-muted">
                Your business is described, your ideal customer is defined and your
                markets are chosen. Next: the companies that match, and why each one is
                worth a conversation.
              </p>
              <Button onClick={leave} loading={finish.isPending}>
                Go to my dashboard
                <ArrowRight aria-hidden className="size-4" />
              </Button>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
