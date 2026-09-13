"use client";
import { useEffect } from "react";
export default function ErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    window.dispatchEvent(
      new CustomEvent("roommateledger:error", {
        detail: { digest: error.digest || "client-render-error" },
      }),
    );
  }, [error]);
  return (
    <main className="app-loading">
      <h1>We couldn’t open your ledger</h1>
      <p>
        Your saved records are still on the server. Try again or reload the
        page.
      </p>
      <button className="primary" onClick={reset}>
        Try again
      </button>
      <button className="text-button" onClick={() => window.location.reload()}>
        Reload RoommateLedger
      </button>
    </main>
  );
}
