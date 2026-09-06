"use client";

import { useRouter } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { Loader2Icon, SparklesIcon } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { articleGenerateFormSchema, type ArticleGenerateFormValues } from "@/lib/validation/blog-writer";
import { useGenerateArticle, useWordpressSites, useWordpressSiteCategories } from "@/hooks/use-blog-writer";
import { useAIGate } from "@/hooks/use-ai-gate";
import { AIRequiredDialog } from "@/components/shared/ai-required-dialog";
import { ApiError } from "@/lib/api/errors";
import { cn } from "@/lib/utils";

const LENGTH_OPTIONS = [
  { value: "short", label: "Breve (~400-600 parole)" },
  { value: "medium", label: "Media (~800-1200 parole)" },
  { value: "long", label: "Lunga (~1500-2000 parole)" },
];

export function AIGenerateForm() {
  const router = useRouter();
  const generateArticle = useGenerateArticle();
  const sitesQuery = useWordpressSites();
  const aiGate = useAIGate();

  const form = useForm<ArticleGenerateFormValues>({
    resolver: zodResolver(articleGenerateFormSchema),
    defaultValues: {
      topic: "",
      description: "",
      goal: "",
      target_audience: "",
      language: "it",
      tone: "professionale e naturale",
      length: "medium",
      primary_keyword: "",
      secondary_keywords: [],
      must_include: "",
      must_avoid: "",
      call_to_action: "",
      hashtag_count: 5,
      wordpress_site_id: null,
      wordpress_category_id: null,
    },
  });

  const selectedSiteId = form.watch("wordpress_site_id") ?? undefined;
  const categoriesQuery = useWordpressSiteCategories(selectedSiteId ?? undefined);

  function onSubmit(values: ArticleGenerateFormValues) {
    aiGate.guard(() => {
      generateArticle.mutate(
        {
          ...values,
          secondary_keywords: values.secondary_keywords,
        },
        {
          onSuccess: (article) => {
            toast.success("Articolo generato: rivedi e modifica il contenuto prima di pubblicarlo");
            router.push(`/blog-writer/${article.id}`);
          },
          onError: (error) => toast.error(error instanceof ApiError ? error.detail : "Generazione non riuscita"),
        }
      );
    });
  }

  return (
    <Card>
      <CardContent className="p-6">
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
            <FormField
              control={form.control}
              name="topic"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Titolo o argomento principale *</FormLabel>
                  <FormControl>
                    <Textarea
                      rows={2}
                      placeholder='Es. "Come l&apos;AI sta trasformando le aziende nel 2026"'
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="description"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Descrizione dell&apos;argomento</FormLabel>
                  <FormControl>
                    <Textarea rows={3} placeholder="Facoltativo: aggiungi contesto o dettagli" {...field} />
                  </FormControl>
                </FormItem>
              )}
            />

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <FormField
                control={form.control}
                name="goal"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Obiettivo dell&apos;articolo</FormLabel>
                    <FormControl>
                      <Input placeholder="Es. informare, convertire, educare" {...field} />
                    </FormControl>
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="target_audience"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Pubblico di riferimento</FormLabel>
                    <FormControl>
                      <Input placeholder="Es. PMI italiane, marketer" {...field} />
                    </FormControl>
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="language"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Lingua</FormLabel>
                    <FormControl>
                      <Input placeholder="it" {...field} />
                    </FormControl>
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="tone"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Tono di voce</FormLabel>
                    <FormControl>
                      <Input placeholder="Es. professionale, amichevole, tecnico" {...field} />
                    </FormControl>
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="length"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Lunghezza desiderata</FormLabel>
                    <Select items={LENGTH_OPTIONS} value={field.value} onValueChange={(v) => field.onChange(v ?? "medium")}>
                      <FormControl>
                        <SelectTrigger className="w-full">
                          <SelectValue />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {LENGTH_OPTIONS.map((o) => (
                          <SelectItem key={o.value} value={o.value}>
                            {o.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="hashtag_count"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Numero indicativo di hashtag</FormLabel>
                    <FormControl>
                      <Input type="number" min={0} max={15} {...field} onChange={(e) => field.onChange(Number(e.target.value))} />
                    </FormControl>
                  </FormItem>
                )}
              />
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <FormField
                control={form.control}
                name="primary_keyword"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Parola chiave principale</FormLabel>
                    <FormControl>
                      <Input {...field} />
                    </FormControl>
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="secondary_keywords"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Parole chiave secondarie</FormLabel>
                    <FormControl>
                      <Input
                        placeholder="Separate da virgola"
                        value={field.value.join(", ")}
                        onChange={(e) =>
                          field.onChange(
                            e.target.value
                              .split(",")
                              .map((k) => k.trim())
                              .filter(Boolean)
                          )
                        }
                      />
                    </FormControl>
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="call_to_action"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Call to action finale</FormLabel>
                    <FormControl>
                      <Input placeholder="Es. Contattaci per una consulenza gratuita" {...field} />
                    </FormControl>
                  </FormItem>
                )}
              />
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <FormField
                control={form.control}
                name="must_include"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Informazioni obbligatorie</FormLabel>
                    <FormControl>
                      <Textarea rows={2} placeholder="Facoltativo" {...field} />
                    </FormControl>
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="must_avoid"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Informazioni da evitare</FormLabel>
                    <FormControl>
                      <Textarea rows={2} placeholder="Facoltativo" {...field} />
                    </FormControl>
                  </FormItem>
                )}
              />
            </div>

            <div className="grid grid-cols-1 gap-4 border-t pt-4 sm:grid-cols-2">
              <FormField
                control={form.control}
                name="wordpress_site_id"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Sito WordPress di destinazione (facoltativo)</FormLabel>
                    <Select
                      items={[{ value: "__none__", label: "Nessuno" }, ...(sitesQuery.data ?? []).map((s) => ({ value: s.id, label: s.name }))]}
                      value={field.value ?? "__none__"}
                      onValueChange={(v) => {
                        field.onChange(v === "__none__" ? null : v);
                        form.setValue("wordpress_category_id", null);
                      }}
                    >
                      <FormControl>
                        <SelectTrigger className="w-full">
                          <SelectValue placeholder="Nessuno" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="__none__">Nessuno</SelectItem>
                        {(sitesQuery.data ?? []).map((s) => (
                          <SelectItem key={s.id} value={s.id}>
                            {s.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormDescription>Solo per orientare la generazione: la pubblicazione resta un passo separato.</FormDescription>
                  </FormItem>
                )}
              />
              {selectedSiteId && (
                <FormField
                  control={form.control}
                  name="wordpress_category_id"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Categoria WordPress (facoltativa)</FormLabel>
                      <Select
                        items={[{ value: "__none__", label: "Nessuna" }, ...(categoriesQuery.data ?? []).map((c) => ({ value: String(c.id), label: c.name }))]}
                        value={field.value ? String(field.value) : "__none__"}
                        onValueChange={(v) => field.onChange(v === "__none__" || !v ? null : Number(v))}
                      >
                        <FormControl>
                          <SelectTrigger className="w-full">
                            <SelectValue placeholder="Nessuna" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          <SelectItem value="__none__">Nessuna</SelectItem>
                          {(categoriesQuery.data ?? []).map((c) => (
                            <SelectItem key={c.id} value={String(c.id)}>
                              {c.name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      {categoriesQuery.isError && (
                        <FormDescription className="text-destructive">
                          Impossibile caricare le categorie da questo sito.
                        </FormDescription>
                      )}
                    </FormItem>
                  )}
                />
              )}
            </div>

            <div className="flex justify-end border-t pt-4">
              <Button
                type="submit"
                disabled={generateArticle.isPending}
                className={cn(!aiGate.configured && "opacity-50")}
              >
                {generateArticle.isPending ? (
                  <Loader2Icon className="size-4 animate-spin" />
                ) : (
                  <SparklesIcon className="size-4" />
                )}
                {generateArticle.isPending ? "Generazione in corso..." : "Genera articolo"}
              </Button>
            </div>
          </form>
        </Form>
      </CardContent>
      <AIRequiredDialog open={aiGate.dialogOpen} onOpenChange={aiGate.setDialogOpen} />
    </Card>
  );
}
