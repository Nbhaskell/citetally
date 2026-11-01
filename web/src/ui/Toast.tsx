import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

export interface ToastAction {
  label: string;
  onClick: () => void;
}

interface ToastItem {
  id: number;
  message: string;
  action?: ToastAction;
}

interface ToastApi {
  show: (message: string, action?: ToastAction) => void;
}

const ToastContext = createContext<ToastApi>({ show: () => undefined });
export const useToast = (): ToastApi => useContext(ToastContext);

const LIFETIME_MS = 8000;

function ToastCard({ item, onDone }: { item: ToastItem; onDone: (id: number) => void }) {
  const timer = useRef<number | undefined>(undefined);
  const start = useCallback(() => {
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => onDone(item.id), LIFETIME_MS);
  }, [item.id, onDone]);
  const stop = () => window.clearTimeout(timer.current);

  useEffect(() => {
    start();
    return stop;
  }, [start]);

  return (
    <div className="toast" onMouseEnter={stop} onMouseLeave={start} onFocus={stop} onBlur={start}>
      <span>{item.message}</span>
      {item.action && (
        <button
          type="button"
          className="link-button"
          onClick={() => {
            item.action?.onClick();
            onDone(item.id);
          }}
        >
          {item.action.label}
        </button>
      )}
      <button type="button" className="link-button" onClick={() => onDone(item.id)}>
        Dismiss
      </button>
    </div>
  );
}

/** Short messages that tell a person what just happened. Announced politely; may carry an Undo. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const next = useRef(1);
  const show = useCallback((message: string, action?: ToastAction) => {
    setItems((current) => [...current.slice(-2), { id: next.current++, message, action }]);
  }, []);
  const done = useCallback(
    (id: number) => setItems((current) => current.filter((item) => item.id !== id)),
    [],
  );
  const api = useMemo(() => ({ show }), [show]);
  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {items.map((item) => (
          <ToastCard key={item.id} item={item} onDone={done} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}
