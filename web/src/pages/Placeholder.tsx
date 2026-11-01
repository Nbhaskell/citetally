import EmptyState from "../ui/EmptyState";

/** Screens that come in a later step still have a place to land, so no link is dead. */
export default function Placeholder({ title }: { title: string }) {
  return (
    <>
      <h1>{title}</h1>
      <EmptyState title="Not built yet">
        This screen arrives in a later step of the interface. The Inbox is ready to use.
      </EmptyState>
    </>
  );
}
