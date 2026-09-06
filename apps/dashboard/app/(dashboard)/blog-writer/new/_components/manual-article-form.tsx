"use client";

import { useRouter } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { Loader2Icon, SaveIcon } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { manualArticleFormSchema, type ManualArticleFormValues } from "@/lib/validation/blog-writer";
import { useCreateArticleManual } from "@/hooks/use-blog-writer";
import { ApiError } from "@/lib/api/errors";

export function ManualArticleForm() {
  const router = useRouter();
  const createArticle = useCreateArticleManual();

  const form = useForm<ManualArticleFormValues>({
    resolver: zodResolver(manualArticleFormSchema),
    defaultValues: {
      title: "",
      slug: "",
      excerpt: "",
      content: "",
      hashtags: [],
      meta_title: "",
      meta_description: "",
      language: "it",
    },
  });

  function onSubmit(values: ManualArticleFormValues) {
    createArticle.mutate(
      {
        title: values.title,
        slug: values.slug || undefined,
        excerpt: values.excerpt || undefined,
        content: values.content,
        hashtags: values.hashtags,
        meta_title: values.meta_title || undefined,
        meta_description: values.meta_description || undefined,
        language: values.language,
      },
      {
        onSuccess: (article) => {
          toast.success("Bozza creata: nessuna AI è stata interpellata");
          router.push(`/blog-writer/${article.id}`);
        },
        onError: (error) => toast.error(error instanceof ApiError ? error.detail : "Creazione non riuscita"),
      }
    );
  }

  return (
    <Card>
      <CardContent className="p-6">
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
            <FormField
              control={form.control}
              name="title"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Titolo *</FormLabel>
                  <FormControl>
                    <Input {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="content"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Contenuto *</FormLabel>
                  <FormControl>
                    <Textarea
                      rows={16}
                      className="font-mono text-xs"
                      placeholder="Scrivi o incolla qui il testo dell'articolo (HTML semplice come <h2>/<p>/<ul> è supportato, ma non è obbligatorio)"
                      {...field}
                    />
                  </FormControl>
                  <FormDescription>Potrai modificarlo di nuovo nell&apos;editor dopo aver salvato.</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="excerpt"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Excerpt / riassunto</FormLabel>
                  <FormControl>
                    <Textarea rows={2} placeholder="Facoltativo" {...field} />
                  </FormControl>
                </FormItem>
              )}
            />

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <FormField
                control={form.control}
                name="slug"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Slug</FormLabel>
                    <FormControl>
                      <Input placeholder="Generato automaticamente dal titolo se lasciato vuoto" {...field} />
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
            </div>

            <FormField
              control={form.control}
              name="hashtags"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Hashtag</FormLabel>
                  <FormControl>
                    <Input
                      placeholder="Separati da virgola, senza # (facoltativo)"
                      value={field.value.join(", ")}
                      onChange={(e) => field.onChange(e.target.value.split(",").map((h) => h.trim()).filter(Boolean))}
                    />
                  </FormControl>
                </FormItem>
              )}
            />

            <div className="grid grid-cols-1 gap-4 border-t pt-4 sm:grid-cols-2">
              <FormField
                control={form.control}
                name="meta_title"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Meta title</FormLabel>
                    <FormControl>
                      <Input {...field} />
                    </FormControl>
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="meta_description"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Meta description</FormLabel>
                    <FormControl>
                      <Input {...field} />
                    </FormControl>
                  </FormItem>
                )}
              />
            </div>

            <div className="flex justify-end border-t pt-4">
              <Button type="submit" disabled={createArticle.isPending}>
                {createArticle.isPending ? <Loader2Icon className="size-4 animate-spin" /> : <SaveIcon className="size-4" />}
                {createArticle.isPending ? "Salvataggio..." : "Salva bozza"}
              </Button>
            </div>
          </form>
        </Form>
      </CardContent>
    </Card>
  );
}
