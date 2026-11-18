import type { ReactNode } from 'react';

/** A part of a settings page: its heading with what it does at the right, what it holds below. */
export function Headed({
  heading,
  action,
  children,
}: {
  heading: string;
  action?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <section aria-label={heading} className="flex flex-col gap-3">
      <div className="flex min-h-9 flex-wrap items-center justify-between gap-2">
        <h2 className="text-base font-semibold">{heading}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

/** A field and its buttons in one row, wrapping under the field where the row is narrow. */
export const inline = 'flex flex-wrap items-end gap-2';
export const inlineField = 'flex min-w-48 flex-1 flex-col gap-1 text-sm';
