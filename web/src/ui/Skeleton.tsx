/** Grey bars where rows will be. Hidden from screen readers, which hear one "Loading" instead. */
export default function Skeleton({ rows = 5, label = "Loading" }: { rows?: number; label?: string }) {
  return (
    <div className="skeleton" role="status" aria-busy="true">
      <span className="sr-only">{label}…</span>
      {Array.from({ length: rows }, (_, i) => (
        <div className="skeleton-row" key={i} aria-hidden="true" />
      ))}
    </div>
  );
}
