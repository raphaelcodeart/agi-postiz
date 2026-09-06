"use client";

import { useEffect } from "react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <html lang="it">
      <body>
        <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: "1rem", fontFamily: "system-ui, sans-serif", textAlign: "center", padding: "1.5rem" }}>
          <h2 style={{ fontSize: "1.125rem", fontWeight: 600 }}>Errore critico dell&apos;applicazione</h2>
          <p style={{ color: "#666", maxWidth: "28rem" }}>
            La dashboard non è riuscita a caricarsi correttamente. Riprova o contatta l&apos;amministratore.
          </p>
          <button
            onClick={reset}
            style={{ padding: "0.5rem 1rem", borderRadius: "0.5rem", background: "#111", color: "#fff", border: "none", cursor: "pointer" }}
          >
            Riprova
          </button>
        </div>
      </body>
    </html>
  );
}
