"use client";

import { AlertTriangle, CheckCircle2, Loader2 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { AuthError, primeCsrf, resendVerification, verifyEmail } from "@/lib/api/auth";

/**
 * Redeems the key from a confirmation email.
 *
 * Verification is mandatory (PRD section 23), so without this page the link in
 * every confirmation email lands on a 404 and no account can ever be used --
 * which is exactly what happened: the mail was being sent to a route that did
 * not exist.
 *
 * The key is redeemed on mount rather than behind a button. The person already
 * expressed intent by clicking the link in their inbox, and asking them to
 * confirm the confirmation is a step that exists only to serve the
 * implementation.
 */

type State = "working" | "done" | "failed";

export default function VerifyEmailPage() {
  const router = useRouter();
  const params = useParams<{ key: string }>();
  const [state, setState] = React.useState<State>("working");
  const [message, setMessage] = React.useState("");
  const [resendTo, setResendTo] = React.useState("");
  const [resent, setResent] = React.useState(false);

  React.useEffect(() => {
    let cancelled = false;

    async function run() {
      const key = decodeURIComponent(params?.key ?? "");
      if (!key) {
        setState("failed");
        setMessage("That link is missing its confirmation code.");
        return;
      }

      await primeCsrf();
      try {
        await verifyEmail(key);
        if (cancelled) return;
        setState("done");
        // Verification signs them in, so send them where they were going.
        setTimeout(() => router.replace("/onboarding"), 1200);
      } catch (caught) {
        if (cancelled) return;
        setState("failed");
        setMessage(
          caught instanceof AuthError
            ? caught.message
            : "That link could not be used. It may have expired.",
        );
      }
    }

    void run();
    return () => {
      cancelled = true;
    };
  }, [params?.key, router]);

  if (state === "working") {
    return (
      <div className="space-y-3 text-center" role="status">
        <Loader2 aria-hidden className="mx-auto size-6 animate-spin text-fg-subtle" />
        <h1 className="text-xl font-semibold tracking-tight text-fg">
          Confirming your email
        </h1>
      </div>
    );
  }

  if (state === "done") {
    return (
      <div className="space-y-3 text-center">
        <div className="mx-auto grid size-11 place-items-center rounded-full bg-positive/15">
          <CheckCircle2 aria-hidden className="size-5 text-positive" />
        </div>
        <h1 className="text-xl font-semibold tracking-tight text-fg">Email confirmed</h1>
        <p className="text-sm text-fg-muted">Taking you to your workspace.</p>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="space-y-3 text-center">
        <div className="mx-auto grid size-11 place-items-center rounded-full bg-negative/10">
          <AlertTriangle aria-hidden className="size-5 text-negative" />
        </div>
        <h1 className="text-xl font-semibold tracking-tight text-fg">
          That link did not work
        </h1>
        <p className="text-sm text-fg-muted">{message}</p>
      </div>

      {resent ? (
        <p role="status" className="text-center text-sm text-positive">
          Sent. Check your inbox.
        </p>
      ) : (
        <form
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault();
            // Deliberately optimistic: reporting whether the address exists
            // would turn this into an account oracle.
            void resendVerification(resendTo).catch(() => undefined);
            setResent(true);
          }}
        >
          <input
            type="email"
            required
            value={resendTo}
            onChange={(event) => setResendTo(event.target.value)}
            placeholder="you@company.com"
            aria-label="Email address"
            className="h-10 w-full rounded-[var(--radius-control)] border border-border bg-surface px-3 text-sm text-fg placeholder:text-fg-subtle"
          />
          <Button type="submit" className="w-full">
            Send a new link
          </Button>
        </form>
      )}

      <p className="text-center text-sm text-fg-muted">
        <Link href="/auth/login" className="font-medium text-accent hover:underline">
          Back to sign in
        </Link>
      </p>
    </div>
  );
}
