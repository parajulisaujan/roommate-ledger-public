"use client";
export default function GlobalError({ reset }: { reset: () => void }) {
  return (
    <html lang="en">
      <body>
        <main>
          <h1>RoommateLedger couldn’t load</h1>
          <p>Please retry. Your saved records have not been removed.</p>
          <button onClick={reset}>Try again</button>
        </main>
      </body>
    </html>
  );
}
