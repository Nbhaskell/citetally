import type { IconName } from "../lib/copy";

// Small outline icons, drawn here so the app loads nothing from outside. Always decorative:
// the word next to an icon carries the meaning.
const PATHS: Record<IconName, string> = {
  clock: "M12 7v5l3 2M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z",
  eye: "M2 12s3.5-6.5 10-6.5S22 12 22 12s-3.5 6.5-10 6.5S2 12 2 12Zm10 3a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z",
  check: "m5 12.5 4.5 4.5L19 7.5",
  close: "m6 6 12 12M18 6 6 18",
  alert: "M12 8v5m0 3.5v.01M10.3 3.9 2.6 17.5A2 2 0 0 0 4.3 20.5h15.4a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z",
  copy: "M9 9h10v11H9zM5 15V4h10",
  block: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18ZM5.6 5.6l12.8 12.8",
  info: "M12 11v6m0-9.5v.01M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z",
  upload: "M12 16V4m0 0L7 9m5-5 5 5M4 20h16",
  camera: "M4 8h3l1.5-2h7L17 8h3v11H4zM12 17a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z",
  file: "M6 3h8l4 4v14H6zM14 3v4h4",
  search: "M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14Zm5-2 5 5",
  retry: "M4 12a8 8 0 0 1 14-5.3L20 9m0-5v5h-5M20 12a8 8 0 0 1-14 5.3L4 15m0 5v-5h5",
  chevron: "m9 6 6 6-6 6",
};

export default function Icon({ name, size = 16 }: { name: IconName; size?: number }) {
  return (
    <svg
      className="icon"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d={PATHS[name]} />
    </svg>
  );
}
