import Link from "next/link";
import { BrandMark, portalFont } from "../_shared/brand";
import { PortalLegalFooter } from "../_shared/legal";

/**
 * Guscio condiviso da /portal/login e /portal/register.
 *
 * Riprende il sistema grafico della landing pubblica (agipost.mamify.ai) invece
 * di quello della dashboard amministrativa - vedi il blocco .portal-skin in
 * app/globals.css per il perche' e per i token. La pagina di accesso
 * dell'amministratore (/login) resta com'e': quella non la vede mai un promoter.
 */

export function PortalAuthShell({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
  footer: React.ReactNode;
}) {
  return (
    <div
      className={`portal-skin ${portalFont.variable} relative flex min-h-screen flex-col items-center justify-center overflow-hidden px-4 py-10`}
    >
      <div aria-hidden className="pa-deco">
        <span className="pa-shape pa-shape--a" />
        <span className="pa-shape pa-shape--b" />
        <span className="pa-shape pa-shape--c" />
      </div>

      <main className="relative z-10 w-full max-w-[26rem]">
        <div className="mb-7 flex flex-col items-center gap-3 text-center">
          <Link href="https://agipost.mamify.ai/" className="pa-brand">
            <BrandMark size={30} />
            AGI Post
          </Link>
          <p className="pa-eyebrow">Un progetto dell&apos;ecosistema Mamify</p>
        </div>

        <div className="pa-card px-6 pt-8 pb-7 sm:px-8">
          <h1 className="pa-title text-center">{title}</h1>
          <p className="mt-2 mb-6 text-center text-[0.95rem] leading-relaxed text-[var(--pa-muted)]">
            {subtitle}
          </p>
          {children}
        </div>

        <div className="mt-5 text-center text-[0.9rem] text-[var(--pa-muted)]">{footer}</div>

        <p className="mt-7 text-center text-[0.82rem] text-[var(--pa-muted)]">
          Niente siti web, niente pacchetti: AGI Post fa una cosa sola, e la fa sui social.
        </p>

        {/* Gli stessi documenti del footer di mamify.ai: il portale non ha
            condizioni proprie. Su una schermata che chiede una password devono
            essere raggiungibili senza cercarli. */}
        <div className="mt-5">
          <PortalLegalFooter compact />
        </div>
      </main>
    </div>
  );
}
