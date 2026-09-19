/**
 * Come una proposta di campagna arriva dentro il wizard di creazione.
 *
 * Solo l'id, in query string: il wizard rilegge la proposta dall'API
 * (`GET /campaign-proposals/{id}`) invece di ricevere il contenuto attraverso
 * sessionStorage come fa il prefill del Blog Writer (lib/blog-writer-prefill.ts).
 * La differenza sta in cosa si sta trasportando: lì è una bozza appena generata
 * che vive solo nel browser, qui è una riga che esiste sul server e che va
 * riletta nel momento in cui la si approva - se il promoter l'ha ritirata o un
 * altro amministratore l'ha già trasformata in campagna, il wizard deve
 * accorgersene, non lavorare su una copia congelata.
 *
 * Di conseguenza il link è anche condivisibile e sopravvive a un refresh.
 */
export const PROPOSAL_PREFILL_PARAM = "fromProposal";

export function proposalPrefillHref(proposalId: string): string {
  return `/campaigns/new?${PROPOSAL_PREFILL_PARAM}=${encodeURIComponent(proposalId)}`;
}
