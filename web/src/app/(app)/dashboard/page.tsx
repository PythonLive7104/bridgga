"use client";

import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { StatTile } from "@/components/ui/stat-tile";
import { useSession } from "@/lib/hooks/use-session";

/**
 * Dashboard layout follows PRD section 116: revenue-shaped metrics on top, the
 * acquisition funnel and live work in the middle, recommendations below.
 *
 * Phase 1 has no prospects, campaigns or deals yet, so every panel shows a
 * real empty state. Seeding the dashboard with invented numbers would make the
 * product look finished and make the first real data impossible to trust.
 */

const FUNNEL_STAGES = [
  "Signup",
  "Onboarding complete",
  "ICP created",
  "First prospect",
  "First campaign",
  "First reply",
  "First opportunity",
  "First meeting",
  "First customer",
];

export default function DashboardPage() {
  const { me, organization, needsOnboarding, needsOrganizationChoice, isLoading } =
    useSession();

  if (isLoading) {
    return (
      <div className="space-y-4" aria-busy>
        <div className="h-8 w-56 animate-pulse rounded bg-bg-subtle" />
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <div
              key={index}
              className="h-28 animate-pulse rounded-[var(--radius-card)] bg-bg-subtle"
            />
          ))}
        </div>
      </div>
    );
  }

  if (needsOnboarding) {
    return (
      <EmptyState
        className="mt-10"
        title="Create your organization to get started"
        description="Everything in Bridgga belongs to an organization: your prospects, campaigns, pipeline and billing. Create one and we will read your website to draft an ICP."
        action={
          <Link
            href="/onboarding"
            className="inline-flex h-10 items-center justify-center rounded-[var(--radius-control)] bg-accent px-5 text-sm font-medium text-accent-fg transition-colors hover:bg-accent-hover"
          >
            Create organization
          </Link>
        }
      />
    );
  }

  if (needsOrganizationChoice) {
    return (
      <EmptyState
        className="mt-10"
        title="Choose an organization"
        description="You belong to more than one organization. Pick which one you are working in -- we will not guess, because the wrong guess writes data into the wrong place."
      />
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-fg">
          {greeting(me?.user.first_name)}
        </h1>
        <p className="mt-1 text-sm text-fg-muted">
          {organization?.name} &middot; nothing has run yet. Start by giving us your
          website.
        </p>
      </div>

      {/* Top row: PRD section 116 leads with outcomes, not activity. */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile label="Customers generated" value="0" hint="The north-star metric" />
        <StatTile label="Pipeline" value="—" hint="Open opportunity value" />
        <StatTile label="Revenue attributed" value="—" hint="Closed won, by campaign" />
        <StatTile label="Meetings booked" value="0" hint="Next 30 days" />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Activation funnel</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {FUNNEL_STAGES.map((stage, index) => {
              const done = index === 0;
              return (
                <div
                  key={stage}
                  className="flex items-center justify-between gap-3 rounded-lg border border-border px-3 py-2"
                >
                  <span className="text-sm text-fg-muted">{stage}</span>
                  <Badge tone={done ? "positive" : "neutral"}>
                    {done ? "Done" : "Not yet"}
                  </Badge>
                </div>
              );
            })}
          </CardContent>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Hot opportunities</CardTitle>
            </CardHeader>
            <CardContent>
              <EmptyState
                title="No scored prospects yet"
                description="Once an ICP exists, the highest-scoring companies with live buying signals surface here."
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Recent conversations</CardTitle>
            </CardHeader>
            <CardContent>
              <EmptyState
                title="No conversations yet"
                description="Replies from every connected channel land in one inbox, classified and summarised."
              />
            </CardContent>
          </Card>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>AI recommendations</CardTitle>
        </CardHeader>
        <CardContent>
          <EmptyState
            title="Not enough data to advise on yet"
            description="The growth advisor needs real funnel data before it can diagnose anything. It will stay quiet rather than invent a recommendation."
          />
        </CardContent>
      </Card>
    </div>
  );
}

function greeting(firstName?: string): string {
  return firstName ? `Welcome back, ${firstName}` : "Welcome back";
}
