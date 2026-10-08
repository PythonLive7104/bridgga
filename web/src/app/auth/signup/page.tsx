"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";

import { SocialAuthButtons } from "@/components/layout/social-auth-buttons";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { AuthError, primeCsrf, signup } from "@/lib/api/auth";

export default function SignupPage() {
  const router = useRouter();

  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = React.useState<Record<string, string>>({});
  const [busy, setBusy] = React.useState(false);
  const [verificationSent, setVerificationSent] = React.useState(false);

  React.useEffect(() => {
    void primeCsrf();
  }, []);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setFieldErrors({});

    try {
      await signup(email, password);
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
      <Card>
        <CardContent className="space-y-3 p-6 text-center">
          <h1 className="text-lg font-semibold tracking-tight text-fg">
            Confirm your email
          </h1>
          <p className="text-sm text-fg-muted">
            We sent a confirmation link to <span className="text-fg">{email}</span>. Open
            it to finish setting up your account.
          </p>
          <p className="text-xs text-fg-subtle">
            Check spam if it has not arrived in a minute or two.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <div className="text-center">
        <h1 className="text-2xl font-semibold tracking-tight text-fg">
          Find your customers
        </h1>
        <p className="mt-1.5 text-sm text-fg-muted">
          Start with your website. No list to upload.
        </p>
      </div>

      <Card>
        <CardContent className="space-y-4 p-6">
          {error ? (
            <p role="alert" className="rounded-lg bg-negative/10 px-3 py-2 text-sm text-negative">
              {error}
            </p>
          ) : null}

          <form className="space-y-4" onSubmit={handleSubmit}>
            <Input
              label="Work email"
              type="email"
              name="email"
              autoComplete="email"
              required
              value={email}
              error={fieldErrors.email}
              onChange={(event) => setEmail(event.target.value)}
            />
            <Input
              label="Password"
              type="password"
              name="password"
              autoComplete="new-password"
              required
              minLength={10}
              hint="At least 10 characters."
              value={password}
              error={fieldErrors.password}
              onChange={(event) => setPassword(event.target.value)}
            />
            <Button type="submit" loading={busy} className="w-full">
              Create account
            </Button>
          </form>

          <div className="flex items-center gap-3">
            <span className="h-px flex-1 bg-border" />
            <span className="text-xs text-fg-subtle">or</span>
            <span className="h-px flex-1 bg-border" />
          </div>

          <SocialAuthButtons disabled={busy} />

          <p className="text-xs text-fg-subtle">
            By creating an account you agree to our{" "}
            <Link href="/terms" className="underline hover:text-fg">
              terms
            </Link>{" "}
            and{" "}
            <Link href="/acceptable-use" className="underline hover:text-fg">
              acceptable use policy
            </Link>
            , which prohibit unsolicited bulk messaging.
          </p>
        </CardContent>
      </Card>

      <p className="text-center text-sm text-fg-muted">
        Already have an account?{" "}
        <Link href="/auth/login" className="font-medium text-accent hover:underline">
          Sign in
        </Link>
      </p>
    </div>
  );
}
