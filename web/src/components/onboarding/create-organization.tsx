"use client";

import { ArrowRight, Building2 } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError } from "@/lib/api/client";
import { useCreateOrganization } from "@/lib/hooks/use-organizations";

/**
 * Step 1 of the section 25 path: create the organization.
 *
 * Everything in the product is tenant-scoped, so until this exists a signed-in
 * user can see nothing: no prospects, no campaigns, no billing.
 *
 * The website is collected here rather than later because it is the input to
 * everything downstream (section 26), and asking for it while someone is
 * already filling in a form about their company costs nothing. Analysis is not
 * started automatically: it crawls several pages and makes an advanced-tier
 * model call, and spending a customer's credits is their decision, one click
 * away on the next screen.
 */

/** The ten launch markets (PRD section 30) with their currencies (section 72). */
const MARKETS: { code: string; name: string; currency: string }[] = [
  { code: "NG", name: "Nigeria", currency: "NGN" },
  { code: "KE", name: "Kenya", currency: "KES" },
  { code: "GH", name: "Ghana", currency: "GHS" },
  { code: "ZA", name: "South Africa", currency: "ZAR" },
  { code: "EG", name: "Egypt", currency: "EGP" },
  { code: "RW", name: "Rwanda", currency: "RWF" },
  { code: "UG", name: "Uganda", currency: "UGX" },
  { code: "TZ", name: "Tanzania", currency: "TZS" },
  { code: "SN", name: "Senegal", currency: "XOF" },
  { code: "CI", name: "Côte d’Ivoire", currency: "XOF" },
];

const OTHER_CURRENCIES = ["USD", "EUR", "GBP"];

/** "https://acme-logistics.com/about" becomes "Acme Logistics". */
function nameFromWebsite(website: string): string {
  const host = website
    .trim()
    .replace(/^https?:\/\//i, "")
    .split("/")[0]
    ?.replace(/^www\./i, "");
  const label = host?.split(".")[0];
  if (!label) return "";
  return label
    .split(/[-_]/)
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

export function CreateOrganizationStep({ onCreated }: { onCreated: () => void }) {
  const createOrganization = useCreateOrganization();

  const [website, setWebsite] = React.useState("");
  const [name, setName] = React.useState("");
  const [nameTouched, setNameTouched] = React.useState(false);
  const [country, setCountry] = React.useState("NG");
  const [currency, setCurrency] = React.useState("NGN");

  const suggestion = nameFromWebsite(website);
  const effectiveName = nameTouched ? name : name || suggestion;

  function onCountryChange(code: string) {
    setCountry(code);
    const market = MARKETS.find((entry) => entry.code === code);
    if (market) setCurrency(market.currency);
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    try {
      await createOrganization.mutateAsync({
        name: effectiveName.trim(),
        country,
        default_currency: currency,
        website: website.trim(),
      });
      // The wizard moves on to reading the site, where the cost is visible
      // before it is spent.
      onCreated();
    } catch {
      // Rendered from the mutation's error state below.
    }
  }

  const error = createOrganization.error;
  const fieldErrors = error instanceof ApiError ? error.fieldErrors : {};

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight text-fg">
          Set up your organization
        </h1>
        <p className="mt-1 text-sm text-fg-muted">
          Everything in Bridgga lives inside an organization: your prospects, campaigns,
          pipeline and billing. You can rename it or add teammates later.
        </p>
      </div>

      {error ? (
        <p
          role="alert"
          className="mb-5 rounded-[var(--radius-control)] bg-negative/10 px-3 py-2 text-sm text-negative"
        >
          {error instanceof Error ? error.message : "That did not work. Try again."}
        </p>
      ) : null}

      <form className="space-y-5" onSubmit={handleSubmit} noValidate>
        <Input
          label="Your website"
          type="url"
          name="website"
          inputMode="url"
          autoFocus
          placeholder="yourcompany.com"
          hint="We read this to work out what you sell and who buys it."
          value={website}
          error={fieldErrors.website?.[0]}
          onChange={(event) => setWebsite(event.target.value)}
        />

        <Input
          label="Organization name"
          name="name"
          required
          placeholder="Acme Logistics"
          value={effectiveName}
          error={fieldErrors.name?.[0]}
          onChange={(event) => {
            setNameTouched(true);
            setName(event.target.value);
          }}
        />

        <div className="grid gap-5 sm:grid-cols-2">
          <div className="flex flex-col gap-1.5">
            <label htmlFor="country" className="text-sm font-medium text-fg">
              Primary market
            </label>
            <select
              id="country"
              value={country}
              onChange={(event) => onCountryChange(event.target.value)}
              className="h-10 rounded-[var(--radius-control)] border border-border bg-surface px-3 text-sm text-fg"
            >
              {MARKETS.map((market) => (
                <option key={market.code} value={market.code}>
                  {market.name}
                </option>
              ))}
              <option value="">Somewhere else</option>
            </select>
            <p className="text-xs text-fg-subtle">
              Where you sell today. We recommend others later.
            </p>
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="currency" className="text-sm font-medium text-fg">
              Currency
            </label>
            <select
              id="currency"
              value={currency}
              onChange={(event) => setCurrency(event.target.value)}
              className="h-10 rounded-[var(--radius-control)] border border-border bg-surface px-3 text-sm text-fg"
            >
              {[...new Set([...MARKETS.map((m) => m.currency), ...OTHER_CURRENCIES])].map(
                (code) => (
                  <option key={code} value={code}>
                    {code}
                  </option>
                ),
              )}
            </select>
            <p className="text-xs text-fg-subtle">What you report revenue in.</p>
          </div>
        </div>

        <Button
          type="submit"
          className="w-full"
          loading={createOrganization.isPending}
          disabled={!effectiveName.trim()}
        >
          <Building2 aria-hidden className="size-4" />
          Create organization
          <ArrowRight aria-hidden className="size-4" />
        </Button>
      </form>

      <p className="mt-6 text-center text-xs text-fg-subtle">
        Next: we read your website and show you what we found, before anything is sent to
        anyone.
      </p>
    </div>
  );
}
