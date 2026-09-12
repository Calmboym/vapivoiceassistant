/**
 * A small colored label for a status string (booking/payment/call/tool-
 * execution). Purely cosmetic — the text shown is always the backend's
 * own status value verbatim (never relabeled), so this never disagrees
 * with what the API actually said.
 */

const OK_STATUSES = new Set([
  "CONFIRMED", "TICKETED", "CHECKED_IN", "COMPLETED", "MODIFIED",
  "PAID", "SUCCEEDED", "ended", "allowed", "success",
]);
const WARN_STATUSES = new Set([
  "CANCELLED", "CANCEL_REQUESTED", "FAILED", "EXPIRED", "REFUNDED", "denied", "error",
]);

function toneFor(status: string): "ok" | "warn" | "neutral" {
  if (OK_STATUSES.has(status)) return "ok";
  if (WARN_STATUSES.has(status)) return "warn";
  return "neutral";
}

const TONE_CLASSES: Record<"ok" | "warn" | "neutral", string> = {
  ok: "bg-ok/10 text-ok border-ok/30",
  warn: "bg-warn/10 text-warn border-warn/30",
  neutral: "bg-mist/10 text-mist border-mist/30",
};

export function StatusBadge({ status }: { status: string }) {
  const tone = toneFor(status);
  return (
    <span
      className={`inline-flex items-center rounded border px-2 py-0.5 text-xs uppercase tracking-wide ${TONE_CLASSES[tone]}`}
    >
      {status.replace(/_/g, " ").toLowerCase()}
    </span>
  );
}
