"use client";

import { useEffect, useState } from "react";
import { Loader2Icon, MailIcon, RefreshCwIcon, SendIcon } from "lucide-react";
import { PRIVACY_URL, TERMS_URL } from "../_shared/legal";

/**
 * La finestra che si para davanti a chi non ha ancora confermato l'indirizzo.
 *
 * Non si chiude, e non ha una via d'uscita che non sia confermare o uscire: e'
 * il punto della cosa. Un avviso richiudibile verrebbe chiuso, e resteremmo con
 * account il cui indirizzo non e' mai stato verificato - cioe' persone che al
 * primo problema non possono ne' essere avvisate ne' recuperare l'accesso.
 *
 * Attenzione pero' a cosa NON e' questo componente: una comodita', non un
 * controllo. Vive nel browser, e chiunque sappia aprire una console puo'
 * scavalcarlo. Il blocco vero sta nell'API, in ``get_verified_portal_user``
 * (apps/api/app/api/v1/portal.py), che risponde 403 a ogni rotta del portale
 * finche' l'indirizzo non e' confermato.
 *
 * Due testi, a seconda che un'email sia gia' partita o no. Chi si e' iscritto
 * prima che la conferma esistesse arriva qui senza aver ricevuto niente:
 * dirgli "controlla la tua email" lo manderebbe a cercare un messaggio che non
 * c'e'. A lui si spiega perche' lo fermiamo e gli si offre l'invio; dopo il
 * primo invio il testo diventa quello di tutti.
 */
export function PortalEmailGate({ email, alreadySent }: { email: string; alreadySent: boolean }) {
  const [sent, setSent] = useState(alreadySent);
  const [pending, setPending] = useState(false);
  const [notice, setNotice] = useState<{ kind: "ok" | "error"; text: string } | null>(null);

  // Con la finestra aperta la pagina sotto non deve scorrere: lo sfondo e'
  // decorativo, e lasciarlo scorrevole darebbe l'impressione di poterci
  // arrivare.
  useEffect(() => {
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, []);

  async function resend() {
    setPending(true);
    setNotice(null);
    try {
      const response = await fetch("/api/portal/auth/resend-verification", { method: "POST" });
      const payload = await response.json().catch(() => null);
      if (response.ok) setSent(true);
      setNotice({
        kind: response.ok ? "ok" : "error",
        text:
          payload?.detail ??
          (response.ok ? "Email inviata." : "Non siamo riusciti a inviare l'email."),
      });
    } catch {
      setNotice({ kind: "error", text: "Servizio non raggiungibile. Riprova fra poco." });
    } finally {
      setPending(false);
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="portal-email-gate-title"
      className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-[rgba(20,19,26,0.55)] px-4 py-8 backdrop-blur-sm"
    >
      <div className="pa-card w-full max-w-[30rem] px-6 py-8 text-center sm:px-9">
        <div className="mx-auto mb-5 flex size-14 items-center justify-center rounded-full bg-[var(--pa-bg-tint)]">
          <MailIcon className="size-6 text-[var(--pa-accent)]" aria-hidden />
        </div>

        {sent ? (
          <>
            <h2 id="portal-email-gate-title" className="pa-title text-[1.45rem]">
              Controlla la tua email
            </h2>

            <p className="mt-3 text-[0.95rem] leading-relaxed text-[var(--pa-ink-2)]">
              Ti abbiamo scritto a <strong className="text-[var(--pa-ink)]">{email}</strong>.
              Apri il messaggio e clicca il link di conferma: serve a verificare che
              l&apos;indirizzo sia tuo e a darti modo di recuperare l&apos;accesso se un giorno
              perdi la password.
            </p>

            <p className="mt-3 text-[0.87rem] leading-relaxed text-[var(--pa-muted)]">
              Finché non confermi, la tua area resta chiusa. Non trovi il messaggio?
              Guarda nella posta indesiderata.
            </p>
          </>
        ) : (
          <>
            <h2 id="portal-email-gate-title" className="pa-title text-[1.45rem]">
              Una conferma per continuare
            </h2>

            <p className="mt-3 text-[0.95rem] leading-relaxed text-[var(--pa-ink-2)]">
              Abbiamo introdotto l&apos;informativa privacy e i termini e condizioni, che
              quando ti sei iscritto non c&apos;erano ancora. Per continuare a usare il portale
              ti chiediamo di accettarli e di confermare il tuo indirizzo.
            </p>

            <p className="mt-3 text-[0.87rem] leading-relaxed text-[var(--pa-muted)]">
              Ti mandiamo un&apos;email a{" "}
              <strong className="text-[var(--pa-ink)]">{email}</strong> con il link: basta un
              clic e la tua area si riapre.
            </p>
          </>
        )}

        {notice && (
          <p
            role="status"
            className={`pa-notice mt-5 text-left ${notice.kind === "error" ? "pa-notice--error" : "pa-notice--ok"}`}
          >
            {notice.text}
          </p>
        )}

        <div className="mt-6 grid gap-3">
          <button type="button" className="pa-btn" onClick={resend} disabled={pending}>
            {pending ? (
              <Loader2Icon className="size-4 animate-spin" />
            ) : sent ? (
              <RefreshCwIcon className="size-4" />
            ) : (
              <SendIcon className="size-4" />
            )}
            {sent ? "Rimandami l\u2019email" : "Inviami l\u2019email"}
          </button>

          {/* Prima del primo invio non c'e' niente da aver gia' confermato. */}
          {sent && (
            <button
              type="button"
              className="text-[0.88rem] font-semibold text-[var(--pa-accent)] hover:underline"
              // Ricarica piena e non router.refresh(): chi ha appena confermato in
              // un'altra scheda ha un cookie nuovo, e il layout va rivalutato dal
              // server con quello in mano.
              onClick={() => window.location.reload()}
            >
              Ho già confermato, aggiorna
            </button>
          )}
        </div>

        <p className="mt-6 text-[0.8rem] leading-relaxed text-[var(--pa-muted)]">
          Il link conferma l&apos;indirizzo e vale come accettazione della{" "}
          <a href={PRIVACY_URL} target="_blank" rel="noreferrer" className="underline underline-offset-4">
            privacy
          </a>{" "}
          e dei{" "}
          <a href={TERMS_URL} target="_blank" rel="noreferrer" className="underline underline-offset-4">
            termini e condizioni
          </a>
          . Indirizzo sbagliato? Esci e registrati con quello giusto, oppure scrivici
          e lo correggiamo noi.
        </p>
      </div>
    </div>
  );
}
