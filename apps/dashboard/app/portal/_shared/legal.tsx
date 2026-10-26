import Link from "next/link";

/**
 * I documenti legali del portale, in un posto solo.
 *
 * Sono gli stessi del footer di mamify.ai e della landing di AGI Post, e devono
 * restare gli stessi: il portale non e' un prodotto a parte con condizioni
 * proprie, e' la stessa cosa vista da dentro. Scritti qui una volta invece che
 * in ogni pagina perche' il giorno che uno di questi indirizzi cambia deve
 * cambiare in un punto - un link legale rotto in fondo a una schermata di
 * registrazione e' esattamente quello che nessuno nota per mesi.
 *
 * Il backend ha le sue copie in PRIVACY_POLICY_URL / TERMS_URL / COOKIE_POLICY_URL
 * (app/core/config.py), perche' le stesse informative vanno linkate anche nelle
 * email, che il browser non lo vedono mai.
 */
export const LEGAL_LINKS = [
  { label: "Termini e condizioni", href: "https://mamify.ai/termini" },
  { label: "Privacy", href: "https://mamify.ai/privacy" },
  { label: "Cookie", href: "https://mamify.ai/cookie" },
] as const;

export const PRIVACY_URL = LEGAL_LINKS[1].href;
export const TERMS_URL = LEGAL_LINKS[0].href;

/**
 * La riga legale in fondo alle pagine del portale.
 *
 * ``compact`` la stringe per le schermate di accesso, dove sta sotto una scheda
 * stretta e non deve rubare attenzione al modulo.
 */
export function PortalLegalFooter({ compact = false }: { compact?: boolean }) {
  return (
    <footer
      className={`flex flex-wrap items-center justify-center gap-x-3 gap-y-1.5 text-center text-[var(--pa-muted)] ${
        compact ? "text-[0.78rem]" : "text-[0.82rem]"
      }`}
    >
      <span>© 2026 Condividiamo Ltd</span>
      <span aria-hidden>·</span>
      {LEGAL_LINKS.map((link, index) => (
        <span key={link.href} className="flex items-center gap-3">
          <Link
            href={link.href}
            target="_blank"
            rel="noreferrer"
            className="underline underline-offset-4 hover:text-[var(--pa-accent)]"
          >
            {link.label}
          </Link>
          {index < LEGAL_LINKS.length - 1 && <span aria-hidden>·</span>}
        </span>
      ))}
    </footer>
  );
}
