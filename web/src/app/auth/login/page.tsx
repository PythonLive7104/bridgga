"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";

import { SocialAuthButtons } from "@/components/layout/social-auth-buttons";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { PasswordField } from "@/components/ui/password-field";
import { useSession } from "@/lib/hooks/use-session";
import {
  AuthError,
  authenticateMfa,
  confirmLoginCode,
  login,
  primeCsrf,
  requestLoginCode,
} from "@/lib/api/auth";

type Stage = "password" | "mfa" | "code-sent";

export default function LoginPage() {
  const router = useRouter();

  const [stage, setStage] = React.useState<Stage>("password");
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [code, setCode] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = React.useState<Record<string, string>>({});
  const [busy, setBusy] = React.useState(false);

  // Django issues the CSRF cookie on a safe request, so fetch one before the
  // first POST rather than letting that POST fail and retry.
  React.useEffect(() => {
    void primeCsrf();
  }, []);

  // Someone who still holds a session does not need this form, and submitting
  // it would only produce a 409. Sending them on is both the honest answer and
  // the one they wanted.
  const { me } = useSession();
  React.useEffect(() => {
    if (me) router.replace(me.memberships.length ? "/dashboard" : "/onboarding");
  }, [me, router]);

  // Where a signed-in user belongs: the dashboard is empty and useless until
  // an organization exists, so someone without one goes to make it.
  const landing = () =>
    me && me.memberships.length === 0 ? "/onboarding" : "/dashboard";
  const toDashboard = () => router.replace(landing());

  function handleFailure(caught: unknown): void {
    if (caught instanceof AuthError) {
      // Not a failure. A stale tab, a back button, or simply a session that
      // outlived the last visit lands here, and telling someone their
      // credentials were wrong while they hold a valid session is the most
      // confusing answer available.
      if (caught.alreadyAuthenticated) {
        toDashboard();
        return;
      }
      if (caught.needsMfa) {
        setStage("mfa");
        setError(null);
        return;
      }
      if (caught.needsEmailVerification) {
        setError("Confirm your email address first. Check your inbox for the link.");
        return;
      }
      setFieldErrors(caught.fieldErrors);
      setError(caught.message);
      return;
    }
    setError("Something went wrong. Please try again.");
  }

  async function run(action: () => Promise<unknown>, onDone?: () => void) {
    setBusy(true);
    setError(null);
    setFieldErrors({});
    try {
      await action();
      onDone?.();
    } catch (caught) {
      handleFailure(caught);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight text-fg">Sign in</h1>
        <p className="mt-1.5 text-sm text-fg-muted">
          Welcome back. Pick up where your pipeline left off.
        </p>
      </div>

      <Card>
        <CardContent className="space-y-4 p-6">
          {error ? (
            <p
              role="alert"
              className="rounded-lg bg-negative/10 px-3 py-2 text-sm text-negative"
            >
              {error}
            </p>
          ) : null}

          {stage === "password" ? (
            <form
              className="space-y-4"
              onSubmit={(event) => {
                event.preventDefault();
                void run(() => login(email, password), toDashboard);
              }}
            >
              <Input
                label="Email"
                type="email"
                name="email"
                autoComplete="email"
                required
                value={email}
                error={fieldErrors.email}
                onChange={(event) => setEmail(event.target.value)}
              />
              <PasswordField
                label="Password"
                name="password"
                autoComplete="current-password"
                required
                value={password}
                error={fieldErrors.password}
                onChange={(event) => setPassword(event.target.value)}
              />
              <Button type="submit" loading={busy} className="w-full">
                Sign in
              </Button>
            </form>
          ) : null}

          {stage === "mfa" ? (
            <form
              className="space-y-4"
              onSubmit={(event) => {
                event.preventDefault();
                void run(() => authenticateMfa(code), toDashboard);
              }}
            >
              <Input
                label="Authentication code"
                inputMode="numeric"
                autoComplete="one-time-code"
                autoFocus
                required
                hint="Six digits from your authenticator app, or a recovery code."
                value={code}
                error={fieldErrors.code}
                onChange={(event) => setCode(event.target.value)}
              />
              <Button type="submit" loading={busy} className="w-full">
                Verify
              </Button>
            </form>
          ) : null}

          {stage === "code-sent" ? (
            <form
              className="space-y-4"
              onSubmit={(event) => {
                event.preventDefault();
                void run(() => confirmLoginCode(code), toDashboard);
              }}
            >
              <Input
                label="Sign-in code"
                inputMode="numeric"
                autoComplete="one-time-code"
                autoFocus
                required
                hint={`We emailed a code to ${email}.`}
                value={code}
                error={fieldErrors.code}
                onChange={(event) => setCode(event.target.value)}
              />
              <Button type="submit" loading={busy} className="w-full">
                Continue
              </Button>
            </form>
          ) : null}

          {stage === "password" ? (
            <>
              <div className="flex items-center gap-3">
                <span className="h-px flex-1 bg-border" />
                <span className="text-xs text-fg-subtle">or</span>
                <span className="h-px flex-1 bg-border" />
              </div>

              <SocialAuthButtons disabled={busy} />

              <Button
                type="button"
                variant="ghost"
                className="w-full"
                disabled={busy || !email}
                onClick={() =>
                  void run(
                    () => requestLoginCode(email),
                    () => setStage("code-sent"),
                  )
                }
              >
                Email me a sign-in code instead
              </Button>
            </>
          ) : null}
        </CardContent>
      </Card>

      <div className="space-y-2 text-center text-sm">
        <p className="text-fg-muted">
          No account?{" "}
          <Link href="/auth/signup" className="font-medium text-accent hover:underline">
            Create one
          </Link>
        </p>
        <p>
          <Link href="/auth/reset-password" className="text-fg-subtle hover:text-fg">
            Forgot your password?
          </Link>
        </p>
      </div>
    </div>
  );
}
