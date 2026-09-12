import type { PageMeta } from "@/lib/adminTypes";

export function Pagination({
  page,
  onPrev,
  onNext,
}: {
  page: PageMeta;
  onPrev: () => void;
  onNext: () => void;
}) {
  const from = page.total === 0 ? 0 : page.offset + 1;
  const to = Math.min(page.offset + page.limit, page.total);
  return (
    <div className="flex items-center justify-between text-xs text-mist mt-4">
      <span>
        {from}–{to} of {page.total}
      </span>
      <div className="flex gap-2">
        <button
          onClick={onPrev}
          disabled={page.offset === 0}
          className="border border-mist/30 rounded px-3 py-1 text-paper disabled:opacity-30 disabled:cursor-not-allowed hover:border-brass transition-colors"
        >
          Previous
        </button>
        <button
          onClick={onNext}
          disabled={!page.has_more}
          className="border border-mist/30 rounded px-3 py-1 text-paper disabled:opacity-30 disabled:cursor-not-allowed hover:border-brass transition-colors"
        >
          Next
        </button>
      </div>
    </div>
  );
}
