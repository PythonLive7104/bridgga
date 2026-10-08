/**
 * The wordmark, in one place.
 *
 * It appears in the marketing header, the app sidebar and the auth screens.
 * Those drifted apart once already — all three carried a hand-rolled letter
 * badge that still read "P" after the rename — so the logo lives here and they
 * render this.
 */

import Image from "next/image";
import Link from "next/link";

import { cn } from "@/lib/utils";

/** Intrinsic size of the source file, used to reserve the right aspect ratio. */
const LOGO_WIDTH = 1600;
const LOGO_HEIGHT = 350;

interface WordmarkProps {
  /** Rendered height in pixels; the width follows from the aspect ratio. */
  height?: number;
  /** Set on the one instance that is above the fold, so it is not lazy-loaded. */
  priority?: boolean;
  className?: string;
}

export function Wordmark({ height = 28, priority = false, className }: WordmarkProps) {
  // Dimensions are given at the size actually rendered, not the source's
  // 1600x350. Next builds its srcset from the declared width, so passing the
  // intrinsic size makes it serve a 1920px-wide file for a 30px-tall logo.
  const width = Math.round((height * LOGO_WIDTH) / LOGO_HEIGHT);

  return (
    <Image
      src="/bridgga-logo-horizontal.png"
      // The link that wraps this names the destination, so the alt text is the
      // product name alone rather than a description a screen reader would
      // announce twice.
      alt="Bridgga"
      width={width}
      height={height}
      priority={priority}
      // Both dimensions are explicit, so the browser reserves the box before
      // the image arrives and nothing shifts (PRD section 103 budgets CLS).
      className={cn("select-none", className)}
    />
  );
}

interface WordmarkLinkProps extends WordmarkProps {
  href?: string;
}

/** The wordmark as a link home. */
export function WordmarkLink({ href = "/", className, ...props }: WordmarkLinkProps) {
  return (
    <Link
      href={href}
      aria-label="Bridgga — home"
      className={cn(
        "inline-flex items-center rounded-md focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-accent",
        className,
      )}
    >
      <Wordmark {...props} />
    </Link>
  );
}
