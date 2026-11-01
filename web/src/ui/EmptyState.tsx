import type { ReactNode } from "react";

/** A designed empty, error or refusal state: what is true, and what the person can do. */
export default function EmptyState({
  title,
  children,
  actions,
  role,
}: {
  title: string;
  children?: ReactNode;
  actions?: ReactNode;
  role?: "alert" | "status";
}) {
  return (
    <section className="empty" role={role}>
      <h2>{title}</h2>
      {children && <p>{children}</p>}
      {actions && <div className="empty-actions">{actions}</div>}
    </section>
  );
}
