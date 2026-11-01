import { useEffect, useId, useRef, type ReactNode } from "react";

/**
 * A modal dialog on the browser's own <dialog>: it traps focus, closes on Escape, and the page
 * behind it is inert. Focus goes back to where it was when the dialog closes.
 */
export default function Dialog({
  title,
  onClose,
  children,
  wide = false,
  side = false,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  wide?: boolean;
  side?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const dialog = ref.current;
    const opener = document.activeElement as HTMLElement | null;
    if (dialog && !dialog.open) dialog.showModal();
    return () => {
      if (dialog?.open) dialog.close();
      if (opener && document.contains(opener)) opener.focus();
    };
  }, []);

  return (
    <dialog
      ref={ref}
      className={`dialog${wide ? " dialog-wide" : ""}${side ? " dialog-side" : ""}`}
      aria-labelledby={titleId}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        if (event.target === ref.current) onClose(); // a click on the backdrop
      }}
    >
      <div className="dialog-body">
        <h2 id={titleId}>{title}</h2>
        {children}
      </div>
    </dialog>
  );
}
