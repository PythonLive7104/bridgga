"use client";

import { Eye, EyeOff } from "lucide-react";
import * as React from "react";

import { Input, type InputProps } from "@/components/ui/input";
import { cn } from "@/lib/utils";

/**
 * A password field with a reveal toggle and an honest strength meter.
 *
 * The meter checks what the server actually enforces
 * (``AUTH_PASSWORD_VALIDATORS``): ten characters, not all digits, and not too
 * close to the email being signed up with. Showing a green bar for something
 * the server then rejects is worse than showing no bar at all, so the rules
 * here are the server's rules and nothing more inventive.
 *
 * The reveal toggle is not a nicety. Most mistyped passwords are caught by
 * looking at them, which is also why the confirmation field exists -- the two
 * controls solve the same problem from different ends, and people reach for
 * different ones.
 */

export interface PasswordStrength {
  score: 0 | 1 | 2 | 3;
  label: string;
  /** What to fix next, or "" when the password satisfies the server's rules. */
  advice: string;
  acceptable: boolean;
}

/** Passwords common enough that Django's CommonPasswordValidator rejects them. */
const OBVIOUS = [
  "password",
  "qwerty",
  "letmein",
  "welcome",
  "admin",
  "iloveyou",
  "monkey",
  "dragon",
  "football",
  "baseball",
  "sunshine",
  "princess",
];

export function scorePassword(password: string, email = ""): PasswordStrength {
  if (!password) {
    return { score: 0, label: "", advice: "", acceptable: false };
  }

  const lower = password.toLowerCase();

  // The server's hard rules first. Each is a refusal, not a weak score, so the
  // meter must not read "good" while the server is about to say no.
  if (password.length < 10) {
    return {
      score: password.length >= 6 ? 1 : 0,
      label: "Too short",
      advice: `${10 - password.length} more character${
        10 - password.length === 1 ? "" : "s"
      } needed.`,
      acceptable: false,
    };
  }

  if (/^\d+$/.test(password)) {
    return {
      score: 1,
      label: "Weak",
      advice: "All digits is refused. Add letters.",
      acceptable: false,
    };
  }

  if (OBVIOUS.some((common) => lower.includes(common))) {
    return {
      score: 1,
      label: "Weak",
      advice: "This contains a very common password.",
      acceptable: false,
    };
  }

  const localPart = email.split("@")[0]?.toLowerCase() ?? "";
  if (localPart.length >= 4 && lower.includes(localPart)) {
    return {
      score: 1,
      label: "Weak",
      advice: "Too close to your email address.",
      acceptable: false,
    };
  }

  // Past the server's rules: everything from here is advice, not a blocker,
  // and the copy says so.
  const variety = [/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z0-9]/].filter((pattern) =>
    pattern.test(password),
  ).length;

  if (password.length >= 16 || variety >= 3) {
    return { score: 3, label: "Strong", advice: "", acceptable: true };
  }

  return {
    score: 2,
    label: "Good",
    advice: "Longer is better than more symbols.",
    acceptable: true,
  };
}

const BAR_COLORS = ["bg-border", "bg-negative", "bg-signal-warm", "bg-positive"] as const;

export function PasswordStrengthMeter({
  strength,
  id,
}: {
  strength: PasswordStrength;
  id?: string;
}) {
  if (!strength.label) return null;

  return (
    <div className="flex flex-col gap-1" id={id}>
      <div className="flex gap-1" aria-hidden>
        {[1, 2, 3].map((step) => (
          <span
            key={step}
            className={cn(
              "h-1 flex-1 rounded-full transition-colors",
              step <= strength.score ? BAR_COLORS[strength.score] : "bg-border",
            )}
          />
        ))}
      </div>
      {/* The bars are decorative; this line is what a screen reader gets.
          Polite, so it does not interrupt typing on every keystroke. */}
      <p role="status" aria-live="polite" className="text-xs text-fg-subtle">
        <span className={strength.acceptable ? "text-fg-muted" : "text-negative"}>
          {strength.label}
        </span>
        {strength.advice ? ` — ${strength.advice}` : null}
      </p>
    </div>
  );
}

export interface PasswordFieldProps extends Omit<InputProps, "type" | "trailing"> {
  /** Render the strength meter under the field. */
  strength?: PasswordStrength;
}

export const PasswordField = React.forwardRef<HTMLInputElement, PasswordFieldProps>(
  function PasswordField({ strength, ...props }, ref) {
    const [revealed, setRevealed] = React.useState(false);
    const Icon = revealed ? EyeOff : Eye;

    return (
      <Input
        ref={ref}
        type={revealed ? "text" : "password"}
        footer={strength ? <PasswordStrengthMeter strength={strength} /> : undefined}
        trailing={
          <button
            type="button"
            onClick={() => setRevealed((current) => !current)}
            // The state is in the label rather than only in the icon, so it is
            // announced and so the control is never a mystery glyph.
            aria-label={revealed ? "Hide password" : "Show password"}
            aria-pressed={revealed}
            className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-fg-subtle transition-colors hover:text-fg focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          >
            <Icon aria-hidden className="size-3.5" />
            {revealed ? "Hide" : "Show"}
          </button>
        }
        {...props}
      />
    );
  },
);
