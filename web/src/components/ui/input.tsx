import * as React from "react";

import { cn } from "@/lib/utils";

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  hint?: string;
  error?: string;
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  function Input({ className, label, hint, error, id, ...props }, ref) {
    const generatedId = React.useId();
    const inputId = id ?? generatedId;
    const describedBy = error
      ? `${inputId}-error`
      : hint
        ? `${inputId}-hint`
        : undefined;

    return (
      <div className="flex flex-col gap-1.5">
        {label ? (
          <label htmlFor={inputId} className="text-sm font-medium text-fg">
            {label}
          </label>
        ) : null}
        <input
          ref={ref}
          id={inputId}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          className={cn(
            "h-10 w-full rounded-[var(--radius-control)] border bg-surface px-3 text-sm",
            "text-fg placeholder:text-fg-subtle",
            "transition-colors focus:outline-none",
            error ? "border-negative" : "border-border hover:border-border-strong",
            className,
          )}
          {...props}
        />
        {error ? (
          <p id={`${inputId}-error`} role="alert" className="text-xs text-negative">
            {error}
          </p>
        ) : hint ? (
          <p id={`${inputId}-hint`} className="text-xs text-fg-subtle">
            {hint}
          </p>
        ) : null}
      </div>
    );
  },
);
