"use client";

import { useState } from "react";
import { SparklesIcon, PencilLineIcon } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { cn } from "@/lib/utils";
import { BlogWriterSubnav } from "../_components/blog-writer-subnav";
import { AIGenerateForm } from "./_components/ai-generate-form";
import { ManualArticleForm } from "./_components/manual-article-form";

type Mode = "ai" | "manual";

const MODES: { value: Mode; label: string; description: string; icon: typeof SparklesIcon }[] = [
  { value: "ai", label: "Genera con AI", description: "Descrivi l'argomento, l'AI scrive una bozza completa", icon: SparklesIcon },
  { value: "manual", label: "Scrivi a mano", description: "Scrivi o incolla il testo: nessuna AI viene interpellata", icon: PencilLineIcon },
];

export default function NewArticlePage() {
  const [mode, setMode] = useState<Mode>("ai");

  return (
    <div className="space-y-6">
      <BlogWriterSubnav />
      <PageHeader
        title="Nuovo articolo"
        description="Genera un articolo con AI, oppure scrivilo o incollalo a mano: la scelta è tua."
      />

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {MODES.map((m) => (
          <button
            key={m.value}
            type="button"
            onClick={() => setMode(m.value)}
            className={cn(
              "flex items-start gap-3 rounded-lg border p-4 text-left transition-colors",
              mode === m.value ? "border-primary bg-primary/5" : "hover:bg-muted"
            )}
          >
            <m.icon className={cn("mt-0.5 size-5 shrink-0", mode === m.value ? "text-primary" : "text-muted-foreground")} />
            <div>
              <p className="text-sm font-medium">{m.label}</p>
              <p className="text-xs text-muted-foreground">{m.description}</p>
            </div>
          </button>
        ))}
      </div>

      {mode === "ai" ? <AIGenerateForm /> : <ManualArticleForm />}
    </div>
  );
}
