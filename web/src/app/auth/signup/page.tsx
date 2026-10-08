"use client";

import { Check, MailCheck } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";

import { SocialAuthButtons } from "@/components/layout/social-auth-buttons";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PasswordField, scorePassword } from "@/components/ui/password-field";
import { AuthError, primeCsrf, signup } from "@/lib/api/auth";

/**
 * Sign-up.
 *
 * The password is entered twice. allauth's headless endpoint takes a single
 * `password`, so the confirmation is checked here and never sent -- it exists
 * to catch a typo before the account is created, because the cost of that typo
 * is an account whose owner cannot sign in and whose email address is already
 * taken.
 *
 * Mismatch is reported on blur, not on every keystroke: told "does not match"
 * after one character of a ten-character password, people learn to ignore the
 * message entirely.
 *
 * The name is optional. A required name field buys a slightly warmer greeting
 * at the cost of a step between someone and the product, and an invented value
 * in the database from anyone who would rather not say.
 */

export default function SignupPage() {
  const router = useRouter();

  const [firstName, setFirstName] = React.useState("");
  const [lastName, setLastName] = React.useState("");
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [confirmation, setConfirmation] = React.useState("");
  const [confirmationTouched, setConfirmationTouched] = React.useState(false);
  const [acceptedTerms, setAcceptedTerms] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = React.useState<Record<string, string>>({});
  const [busy, setBusy] = React.useState(false);
  const [verificationSent, setVerificationSent] = React.useState(false);

  React.useEffect(() => {
    void primeCsrf();
  }, []);

  const strength = scorePassword(password, email);
  const matches = password === confirmation;
  const mismatch = confirmationTouched && confirmation.length > 0 && !matches;
  const canSubmit =
    Boolean(email) &&
    strength.acceptable &&
    matches &&
    confirmation.length > 0 &&
    acceptedTerms;

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();

    if (!matches) {
      setConfirmationTouched(true);
      return;
    }

    setBusy(true);
    setError(null);
    setFieldErrors({});

    try {
      await signup({
        email,
        password,
        first_name: firstName,
        last_name: lastName,
      });
      router.replace("/onboarding");
    } catch (caught) {
      if (caught instanceof AuthError) {
        // Verification required is the expected success path, not a failure:
        // the account exists, it just cannot sign in until confirmed.
        if (caught.needsEmailVerification) {
          setVerificationSent(true);
          return;
        }
        setFieldErrors(caught.fieldErrors);
        setError(caught.message);
        return;
      }
      setError("Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  if (verificationSent) {
    return (
      <div className="space-y-3 text-center">
        <div className="mx-auto grid size-11 place-items-center rounded-full bg-accent-subtle">
          <MailCheck aria-hidden className="size-5 text-accent" />
        </div>
        <h1 className="text-xl font-semibold tracking-tight text-fg">
          Confirm your email
        </h1>
        <p className="text-sm text-fg-muted">
          We sent a confirmation link to <span className="text-fg">{email}</span>. Open it
          to finish setting up your account.
        </p>
        <p className="text-xs text-fg-subtle">
          Check spam if it has not arrived in a minute or two.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight text-fg">
          Create your account
        </h1>
        <p className="mt-1.5 text-sm text-fg-muted">
          Start with your website. There is no list to upload.
        </p>
      </div>

      {error ? (
        <p
          role="alert"
          className="rounded-[var(--radius-control)] bg-negative/10 px-3 py-2 text-sm text-negative"
        >
          {error}
        </p>
      ) : null}

      {/* Social first: for anyone with a Google or Microsoft account this is
          one click, and putting it under a form they need not fill in presents
          the slower path as the main one. */}
      <SocialAuthButtons disabled={busy} />

      <div className="flex items-center gap-3">
        <span className="h-px flex-1 bg-border" />
        <span className="text-xs text-fg-subtle">or use your email</span>
        <span className="h-px flex-1 bg-border" />
      </div>

      <form className="space-y-4" onSubmit={handleSubmit} noValidate>
        <div className="grid gap-4 sm:grid-cols-2">
          <Input
            label="First name"
            name="first_name"
            autoComplete="given-name"
            placeholder="Ada"
            value={firstName}
            onChange={(event) => setFirstName(event.target.value)}
          />
          <Input
            label="Last name"
            name="last_name"
            autoComplete="family-name"
            placeholder="Lovelace"
            value={lastName}
            onChange={(event) => setLastName(event.target.value)}
          />
        </div>

        <Input
          label="Work email"
          type="email"
          name="email"
          autoComplete="email"
          placeholder="you@company.com"
          required
          value={email}
          error={fieldErrors.email}
          onChange={(event) => setEmail(event.target.value)}
        />

        <PasswordField
          label="Password"
          name="password"
          autoComplete="new-password"
          placeholder="At least 10 characters"
          required
          value={password}
          error={fieldErrors.password}
          strength={strength}
          onChange={(event) => setPassword(event.target.value)}
        />

        <PasswordField
          label="Confirm password"
          name="password_confirmation"
          autoComplete="new-password"
          placeholder="Re-enter password"
          required
          value={confirmation}
          onBlur={() => setConfirmationTouched(true)}
          error={mismatch ? "The two passwords do not match." : undefined}
          onChange={(event) => setConfirmation(event.target.value)}
          footer={
            confirmation.length > 0 && matches ? (
              <p className="flex items-center gap-1 text-xs text-positive">
                <Check aria-hidden className="size-3.5" />
                Passwords match
              </p>
            ) : undefined
          }
        />

        {/* An explicit tick, not an implicit line of small print. The policy
            being agreed to is the one that forbids unsolicited bulk messaging
            (PRD sections 62-63), and that is worth a deliberate act. */}
        <label className="flex cursor-pointer items-start gap-2.5 text-sm text-fg-muted">
          <input
            type="checkbox"
            name="terms"
            checked={acceptedTerms}
            onChange={(event) => setAcceptedTerms(event.target.checked)}
            className="mt-0.5 size-4 shrink-0 rounded border-border accent-[var(--accent)]"
          />
          <span>
            I agree to the{" "}
            <Link href="/terms" className="text-accent hover:underline">
              terms
            </Link>{" "}
            and{" "}
            <Link href="/acceptable-use" className="text-accent hover:underline">
              acceptable use policy
            </Link>
            , which prohibit unsolicited bulk messaging.
          </span>
        </label>

        <Button type="submit" loading={busy} disabled={!canSubmit} className="w-full">
          Create account
        </Button>
      </form>

      <p className="text-center text-sm text-fg-muted">
        Already have an account?{" "}
        <Link href="/auth/login" className="font-medium text-accent hover:underline">
          Sign in
        </Link>
      </p>
    </div>
  );
}
