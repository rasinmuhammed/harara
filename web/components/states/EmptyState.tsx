export function EmptyState() {
  return (
    <div className="flex min-h-[440px] flex-col items-center justify-center rounded-lg border border-dashed border-border-strong bg-surface px-6 py-12 text-center">
      <svg
        width="180"
        height="90"
        viewBox="0 0 180 90"
        fill="none"
        aria-hidden
        className="mb-5 text-border-strong"
      >
        <path d="M12 78h156M12 78V10" stroke="currentColor" strokeWidth="1.4" />
        <path
          d="M12 62c22-4 34-30 52-30s26 20 44 18 30-26 60-30"
          stroke="currentColor"
          strokeWidth="1.4"
          strokeDasharray="3 5"
        />
      </svg>
      <h2 className="text-h3 text-ink">Plan a shift</h2>
      <p className="mt-2 max-w-sm text-ink-secondary">
        Choose a location and day on the left, then plan. You&rsquo;ll see the
        forecast WBGT for the day and how the optimiser&rsquo;s work/rest plan
        compares with the fixed calendar ban.
      </p>
    </div>
  );
}
