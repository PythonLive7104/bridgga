"use client";

import { Check, Loader2 } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { apiFetch } from "@/lib/api/client";

/**
 * Unsubscribe (PRD section 63).
 *
 * The whole page is one button. A person who clicked "unsubscribe" in a mail
 * client has already decided; anything between them and that outcome — a
 * login, a confirmation, a survey, a preference centre — is a dark pattern
 * with a spam complaint attached, because the alternative control they reach
 * for next is the one that reports the sender.
 *
 * The reason box appears *after* it is done, for anybody who wants to say
 * why. It is never a condition of leaving.
 */

interface Described {
  valid: boolean;
  address: string;
  organization: string;
  already_unsubscribed: boolean;
}

export function UnsubscribeForm({ token }: { token: string }) {
  const [described, setDescribed] = React.useState<Described | null>(null);
  const [done, setDone] = React.useState(false);
  const [working, setWorking] = React.useState(false);
  const [reason, setReason] = React.useState("");
  const [reasonSent, setReasonSent] = React.useState(false);

  React.useEffect(() => {
    apiFetch<Described>(`/api/v1/unsubscribe/${token}`)
      .then((result) => {
        setDescribed(result);
        if (result.already_unsubscribed) setDone(true);
      })
      // A token that will not describe itself still has to be able to
      // unsubscribe, so a failure here never blocks the button below.
      .catch(() =>
        setDescribed({
          valid: false,
          address: "",
          organization: "",
          already_unsubscribed: false,
        }),
      );
  }, [token]);

  async function unsubscribe(withReason = false) {
    setWorking(true);
    try {
      await apiFetch(`/api/v1/unsubscribe/${token}`, {
        method: "POST",
        body: withReason ? { reason } : {},
      });
      setDone(true);
      if (withReason) setReasonSent(true);
    } finally {
      setWorking(false);
    }
  }

  const sender = described?.organization ? ` from ${described.organization}` : "";

  return (
    <div className="mx-auto max-w-lg px-4 py-20">
      <Card>
        <CardContent className="space-y-5 p-6">
          {done ? (
            <>
              <h1 className="flex items-center gap-2 text-xl font-semibold text-fg">
                <Check aria-hidden className="size-5 text-positive" />
                You are unsubscribed
              </h1>
              <p className="text-sm text-fg-muted">
                {described?.address ? `${described.address} will ` : "You will "}
                not receive further messages{sender}. It takes effect immediately and
                applies to every campaign, not just this one.
              </p>

              {reasonSent ? (
                <p className="text-sm text-fg-subtle">Thank you — that is noted.</p>
              ) : (
                <div className="space-y-2 border-t border-border pt-4">
                  <label htmlFor="reason" className="text-sm text-fg-muted">
                    If you would like to say why, it helps. Entirely optional.
                  </label>
                  <textarea
                    id="reason"
                    rows={3}
                    value={reason}
                    onChange={(event) => setReason(event.target.value)}
                    className="w-full rounded-[var(--radius-control)] border border-border bg-surface px-3 py-2 text-sm text-fg"
                    placeholder="Too many emails, not relevant, wrong person…"
                  />
                  <Button
                    variant="secondary"
                    size="sm"
                    disabled={!reason.trim()}
                    loading={working}
                    onClick={() => unsubscribe(true)}
                  >
                    Send feedback
                  </Button>
                </div>
              )}
            </>
          ) : (
            <>
              <h1 className="text-xl font-semibold text-fg">Unsubscribe{sender}</h1>
              <p className="text-sm text-fg-muted">
                {described?.address
                  ? `This stops all messages to ${described.address}.`
                  : "This stops all messages to your address."}{" "}
                One click, no account needed.
              </p>
              <Button
                onClick={() => unsubscribe(false)}
                loading={working}
                className="w-full"
              >
                {working ? <Loader2 aria-hidden className="size-4 animate-spin" /> : null}
                Unsubscribe me
              </Button>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
