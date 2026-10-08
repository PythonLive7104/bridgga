"use client";

import { ArrowRight, FileText, Quote, Radar } from "lucide-react";
import { usePathname } from "next/navigation";

/**
 * The panel beside the auth forms.
 *
 * Sign-up and sign-in get different artwork and different copy, because the
 * two readers are not the same person. Someone signing up may never have seen
 * the product and needs to know what it does; someone signing in already
 * knows, so that side carries what the product is *for* rather than a pitch.
 *
 * The artwork is drawn here rather than photographed. Stock photography of
 * "African business" is both a licensing liability and a cliché, and a
 * generic boardroom says nothing about what this software does. These say
 * something: one is the ten launch markets, the other is the evidence trail
 * that is the actual product claim. Both are a few KB, both follow the theme,
 * and neither goes blurry on a high-density screen.
 */

/** The ten launch markets (PRD section 30). */
const MARKETS = [
  "Nigeria",
  "Kenya",
  "Ghana",
  "South Africa",
  "Egypt",
  "Rwanda",
  "Uganda",
  "Tanzania",
  "Senegal",
  "Côte d'Ivoire",
];

/**
 * A deliberately coarse, dot-matrix Africa.
 *
 * Stylised rather than cartographic on purpose: a low-fidelity map that is
 * obviously a graphic reads as a decision, where a half-accurate outline just
 * reads as a bad map. `#` is land, `o` is a highlighted launch market, and the
 * lone column on the right is Madagascar.
 */
const AFRICA = [
  "..######.......",
  ".#########.....",
  ".##########....",
  "..##########...",
  ".###########...",
  "####o#######...",
  "###########o...",
  ".####o######...",
  "..####o#####o..",
  "..##########o..",
  "...####o#####..",
  "....####o####..",
  "....#########..",
  "....########...",
  "....#######..#.",
  ".....######..#.",
  ".....#####...#.",
  "......####...#.",
  "......o###.....",
  ".......###.....",
  ".......##......",
  "........#......",
];

const CELL = 9;
const DOT = 2.6;

function AfricaMap() {
  // Widest row rather than the first: the rows are hand-drawn, and reading
  // one of them would clip the map if that row were ever the short one.
  const columns = AFRICA.reduce((widest, row) => Math.max(widest, row.length), 0);
  const width = columns * CELL;
  const height = AFRICA.length * CELL;

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="h-auto w-full max-w-[22rem]"
      role="img"
      aria-label="A stylised map of Africa with the ten launch markets marked."
    >
      {AFRICA.flatMap((row, y) =>
        [...row].map((cell, x) => {
          if (cell === ".") return null;
          const highlighted = cell === "o";
          return (
            <circle
              key={`${x}-${y}`}
              cx={x * CELL + CELL / 2}
              cy={y * CELL + CELL / 2}
              r={highlighted ? DOT * 1.5 : DOT}
              className={highlighted ? "fill-accent" : "fill-fg"}
              opacity={highlighted ? 1 : 0.22}
            />
          );
        }),
      )}
    </svg>
  );
}

/**
 * The evidence trail, drawn as the product actually renders it: a claim, the
 * line it was read from, and where. PRD section 58 is the reason this exists
 * at all, so it is the right thing to show someone returning to the product.
 */
function EvidenceTrail() {
  return (
    <div className="w-full max-w-sm space-y-3" aria-hidden>
      <div className="rounded-[var(--radius-card)] border border-border bg-surface/70 p-4 shadow-[var(--shadow-card)] backdrop-blur">
        <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-accent">
          <Radar className="size-3.5" />
          Hiring
        </div>
        <p className="mt-2 text-sm text-fg">
          Opened three fleet-supervisor roles in Lagos this month.
        </p>
        <div className="mt-3 flex items-center gap-2 border-t border-border/70 pt-2 text-xs text-fg-subtle">
          <Quote className="size-3" />
          <span className="truncate">careers page · read 2 days ago</span>
        </div>
      </div>

      <div className="flex items-center gap-2 pl-4 text-xs text-fg-subtle">
        <span className="h-6 w-px bg-border" />
        <ArrowRight className="size-3.5" />
        becomes a reason to write
      </div>

      <div className="rounded-[var(--radius-card)] border border-border bg-surface/70 p-4 shadow-[var(--shadow-card)] backdrop-blur">
        <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-fg-muted">
          <FileText className="size-3.5" />
          Why contact them
        </div>
        <p className="mt-2 text-sm text-fg">
          They are scaling the exact operation your product measures — and they are hiring
          for the problem you solve.
        </p>
      </div>
    </div>
  );
}

interface Showcase {
  eyebrow: string;
  headline: string;
  body: string[];
  art: React.ReactNode;
  footer: React.ReactNode;
}

const SHOWCASES: Record<"signup" | "signin", Showcase> = {
  signup: {
    eyebrow: "Built for African B2B",
    headline: "Turn your website into a customer acquisition engine.",
    body: [
      "Give us your website. We read what you sell, who you sell it to and how you make money, then draft the profile of the companies most likely to need it — and you correct anything we got wrong.",
      "From there we search your markets for companies that match, watch for the events that mean they need you now, and tell you why each one is worth a conversation today. Every claim arrives with the page it came from and the date we read it.",
    ],
    art: <AfricaMap />,
    footer: (
      <ul className="flex flex-wrap gap-x-3 gap-y-1.5 text-xs text-fg-subtle">
        {MARKETS.map((market) => (
          <li key={market}>{market}</li>
        ))}
      </ul>
    ),
  },
  signin: {
    eyebrow: "Welcome back",
    headline: "Evidence, not guesses.",
    body: [
      "Your pipeline is where you left it. Prospects carry the signals that surfaced them, the research behind them, and the reason to reach out — each one traceable to the source it came from.",
      "And when a deal closes, it is joined back to the campaign that started it, so you can answer the only question that matters: which of this is actually making money?",
    ],
    art: <EvidenceTrail />,
    footer: (
      <p className="text-xs text-fg-subtle">
        Compliant outreach only. We do not sell scraped personal data.
      </p>
    ),
  },
};

export function AuthShowcase({ variant }: { variant: "signup" | "signin" }) {
  const { eyebrow, headline, body, art, footer } = SHOWCASES[variant];

  return (
    <div className="relative flex h-full flex-col">
      {/* Grid wash. Texture only, so it is hidden from assistive technology
          and can never intercept a click meant for the content. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 -z-10 opacity-40"
        style={{
          backgroundImage:
            "linear-gradient(to right, var(--border) 1px, transparent 1px), linear-gradient(to bottom, var(--border) 1px, transparent 1px)",
          backgroundSize: "56px 56px",
          maskImage: "radial-gradient(ellipse 80% 60% at 30% 40%, black, transparent)",
          WebkitMaskImage:
            "radial-gradient(ellipse 80% 60% at 30% 40%, black, transparent)",
        }}
      />
      <div
        aria-hidden
        className="pointer-events-none absolute -left-32 top-1/4 -z-10 size-[32rem] rounded-full bg-accent/10 blur-3xl"
      />

      <div className="my-auto max-w-xl py-10">
        <p className="text-xs font-medium uppercase tracking-[0.12em] text-accent">
          {eyebrow}
        </p>
        <h2 className="mt-3 text-balance text-4xl font-semibold leading-tight tracking-tight text-fg">
          {headline}
        </h2>
        {body.map((paragraph) => (
          <p
            key={paragraph.slice(0, 32)}
            className="mt-4 text-pretty text-[0.9375rem] leading-relaxed text-fg-muted"
          >
            {paragraph}
          </p>
        ))}

        <div className="mt-10 flex justify-start">{art}</div>

        <div className="mt-8">{footer}</div>
      </div>
    </div>
  );
}

/**
 * Picks the panel from the route, so the layout can stay a server component
 * and neither page has to remember to pass its own variant.
 */
export function AuthPanel() {
  const pathname = usePathname();
  return <AuthShowcase variant={pathname?.includes("/signup") ? "signup" : "signin"} />;
}
