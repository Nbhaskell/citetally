// Money arrives as integer minor units and is shown without ever becoming a float:
// the digits are split with BigInt, so $1,240.05 is never 1240.0500000000002.

const SYMBOLS: Record<string, string> = { USD: "$", EUR: "€", GBP: "£", JPY: "¥", CAD: "CA$", AUD: "A$" };
const ZERO_DECIMAL = new Set(["JPY", "KRW", "VND", "CLP", "ISK"]);

const MINUS = "−"; // a real minus sign, which a screen reader says as "minus"

export function decimals(currency: string): number {
  return ZERO_DECIMAL.has(currency) ? 0 : 2;
}

function group(digits: string): string {
  return digits.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

export interface MoneyOptions {
  /** A credit note is stored positive and shown negative. */
  credit?: boolean;
  /** Leave the symbol off, for a column whose heading names the currency. */
  bare?: boolean;
}

/** "$1,240.05", "−$45.00", "¥1,500". Null (nothing printed) is an empty string. */
export function formatMinor(
  minor: number | null | undefined,
  currency: string,
  options: MoneyOptions = {},
): string {
  if (minor === null || minor === undefined) return "";
  const places = decimals(currency);
  const negative = (minor < 0) !== Boolean(options.credit) && minor !== 0;
  const absolute = BigInt(Math.abs(minor));
  const scale = 10n ** BigInt(places);
  const whole = group((absolute / scale).toString());
  const fraction = places ? "." + (absolute % scale).toString().padStart(places, "0") : "";
  const symbol = options.bare ? "" : (SYMBOLS[currency] ?? currency + " ");
  return `${negative ? MINUS : ""}${symbol}${whole}${fraction}`;
}
