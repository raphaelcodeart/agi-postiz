import { Inter } from "next/font/google";

/**
 * Pezzi d'identita' condivisi da tutto il portale promoter - le pagine di
 * accesso del gruppo (public) e la dashboard del gruppo (app).
 *
 * La cartella ha il prefisso "_" perche' Next.js la escluda dal routing: e'
 * codice condiviso, non una rotta. Sta qui e non dentro uno dei due gruppi
 * perche' appartiene a entrambi: due copie dello stesso marchio finirebbero
 * per divergere.
 */

/** Inter e' il carattere della landing; la dashboard amministrativa usa Geist.
 *  Caricato qui e non nel layout radice perche' lo vogliamo solo sotto /portal. */
export const portalFont = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

/** Il marchio della landing (/assets/img/mark.svg di agipost.mamify.ai),
 *  ridisegnato inline per non dipendere da un file servito da un altro host. */
export function BrandMark({ size = 44 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" role="img" aria-label="AGI Post">
      <defs>
        <linearGradient id="pa-mark" x1="6" y1="58" x2="58" y2="6" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#7C6BD8" />
          <stop offset=".38" stopColor="#4FB3F5" />
          <stop offset=".72" stopColor="#F2685E" />
          <stop offset="1" stopColor="#F6B25A" />
        </linearGradient>
      </defs>
      <circle cx="14" cy="32" r="6.4" fill="none" stroke="url(#pa-mark)" strokeWidth="4.6" />
      <circle cx="46" cy="16" r="6.4" fill="none" stroke="url(#pa-mark)" strokeWidth="4.6" />
      <circle cx="46" cy="48" r="6.4" fill="none" stroke="url(#pa-mark)" strokeWidth="4.6" />
      <path
        d="M19.6 29.2 40.4 18.8M19.6 34.8 40.4 45.2"
        fill="none"
        stroke="url(#pa-mark)"
        strokeWidth="4.2"
        strokeLinecap="round"
      />
    </svg>
  );
}
