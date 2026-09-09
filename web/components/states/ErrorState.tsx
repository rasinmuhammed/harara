export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <div
      role="alert"
      className="flex min-h-[440px] flex-col items-center justify-center rounded-lg border border-border-strong bg-surface px-6 py-12 text-center"
    >
      <svg
        width="44"
        height="44"
        viewBox="0 0 24 24"
        fill="none"
        aria-hidden
        className="mb-4 text-state-stop"
      >
        <path
          d="M4 17 9 8l3 5 2-3 6 7"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          d="M3 21h18"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
        />
      </svg>
      <h2 className="text-h3 text-ink">Couldn&rsquo;t reach the planner</h2>
      <p className="mt-2 max-w-sm text-ink-secondary">{message}</p>
      <button
        type="button"
        onClick={onRetry}
        className="mt-5 rounded bg-accent px-4 py-2.5 text-base font-semibold text-on-accent transition-colors duration-[var(--dur-1)] hover:bg-accent-hover"
      >
        Try again
      </button>
      <p className="mt-3 text-sm text-ink-muted">
        If this persists, the API may be redeploying — give it a minute.
      </p>
    </div>
  );
}
