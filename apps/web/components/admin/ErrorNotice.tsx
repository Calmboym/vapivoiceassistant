/**
 * Renders an ApiRequestError's message verbatim (it's already an
 * already-user-safe string by the time it reaches here — see
 * app/core/exceptions.py's "never leak a stack trace" discipline on the
 * backend, which is what makes it safe to render directly without a
 * generic "something went wrong" substitution).
 */
export function ErrorNotice({ message }: { message: string }) {
  return (
    <div className="border border-warn/40 bg-warn/5 text-warn rounded-lg px-4 py-3 text-sm">
      {message}
    </div>
  );
}
