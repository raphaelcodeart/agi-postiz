import { cn } from "@/lib/utils";

// Splits on URLs (capturing group keeps them in the output array, interleaved
// with the surrounding plain-text segments).
const URL_REGEX = /(https?:\/\/[^\s]+)/g;
// Trailing punctuation that regularly follows a URL in a sentence but isn't
// part of it (e.g. "...iscriviti qui: https://esempio.com." should link only
// up to ".com", not swallow the closing period).
const TRAILING_PUNCTUATION = /[.,;:!?)\]}'"]+$/;

function splitTrailingPunctuation(url: string): [string, string] {
  const match = url.match(TRAILING_PUNCTUATION);
  if (!match) return [url, ""];
  return [url.slice(0, -match[0].length), match[0]];
}

/**
 * Renders campaign/post text with any http(s) URL turned into a real
 * clickable link - needed because resolved_text is plain text server-side
 * (e.g. the referral link campaign_resolver.py appends as "ISCRIVITI QUI:
 * {url}" is just a string, not markup) and a browser never auto-linkifies
 * plain text on its own. Used by the Bacheca feed and the publication detail
 * page's "Testo risolto" card.
 */
export function LinkifiedText({ text, className }: { text: string; className?: string }) {
  const parts = text.split(URL_REGEX);
  return (
    <p className={cn("whitespace-pre-wrap text-sm", className)}>
      {parts.map((part, i) => {
        if (part.startsWith("http://") || part.startsWith("https://")) {
          const [href, trailing] = splitTrailingPunctuation(part);
          return (
            <span key={i}>
              <a href={href} target="_blank" rel="noopener noreferrer" className="text-primary underline underline-offset-2 hover:no-underline">
                {href}
              </a>
              {trailing}
            </span>
          );
        }
        return <span key={i}>{part}</span>;
      })}
    </p>
  );
}
