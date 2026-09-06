"use client";

import { useState } from "react";
import { toast } from "sonner";
import { PlusIcon, Trash2Icon, BookOpenIcon } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { EmptyState } from "@/components/shared/empty-state";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useCreateKnowledgeDocument, useDeleteKnowledgeDocument, useKnowledgeDocuments } from "@/hooks/use-omnichannel";
import { ApiError } from "@/lib/api/client";
import { formatDateTime } from "@/lib/format";

export default function OmnichannelKnowledgeBasePage() {
  const { data: documents, isLoading } = useKnowledgeDocuments();
  const createDocument = useCreateKnowledgeDocument();
  const deleteDocument = useDeleteKnowledgeDocument();

  const [createOpen, setCreateOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [deleteId, setDeleteId] = useState<string | null>(null);

  function handleCreate() {
    if (!title.trim() || !content.trim()) {
      toast.error("Titolo e contenuto sono obbligatori");
      return;
    }
    createDocument.mutate(
      { title, content_text: content, source_type: "manual" },
      {
        onSuccess: () => {
          toast.success("Documento aggiunto alla knowledge base");
          setTitle("");
          setContent("");
          setCreateOpen(false);
        },
        onError: (err) => toast.error(err instanceof ApiError ? err.message : "Impossibile salvare il documento"),
      }
    );
  }

  return (
    <div>
      <PageHeader
        title="Knowledge Base"
        description="Informazioni aziendali (FAQ, prezzi, procedure...) che l'AI usa per generare risposte più accurate."
        actions={<Button onClick={() => setCreateOpen(true)}><PlusIcon /> Nuovo documento</Button>}
      />

      {isLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-16" />
          <Skeleton className="h-16" />
        </div>
      ) : !documents || documents.length === 0 ? (
        <EmptyState
          icon={BookOpenIcon}
          title="Nessun documento"
          description="Aggiungi FAQ, prezzi o procedure aziendali: l'AI le userà come riferimento nelle risposte."
          action={<Button onClick={() => setCreateOpen(true)}><PlusIcon /> Nuovo documento</Button>}
        />
      ) : (
        <div className="space-y-3">
          {documents.map((doc) => (
            <div key={doc.id} className="rounded-lg border p-4">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="text-sm font-medium">{doc.title}</p>
                  <p className="text-xs text-muted-foreground">Aggiunto il {formatDateTime(doc.created_at)}</p>
                </div>
                <Button size="icon-sm" variant="ghost" className="text-destructive hover:text-destructive" onClick={() => setDeleteId(doc.id)}>
                  <Trash2Icon />
                </Button>
              </div>
              {doc.content_text && <p className="mt-2 line-clamp-3 text-sm text-muted-foreground">{doc.content_text}</p>}
            </div>
          ))}
        </div>
      )}

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Nuovo documento</DialogTitle>
            <DialogDescription>Testo libero: FAQ, listino prezzi, procedure, policy aziendali...</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label>Titolo</Label>
              <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Es. Politica di reso" />
            </div>
            <div className="space-y-1.5">
              <Label>Contenuto</Label>
              <Textarea value={content} onChange={(e) => setContent(e.target.value)} rows={8} placeholder="Scrivi qui il contenuto..." />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>Annulla</Button>
            <Button onClick={handleCreate} disabled={createDocument.isPending}>Salva</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={!!deleteId}
        onOpenChange={(open) => !open && setDeleteId(null)}
        title="Eliminare questo documento?"
        description="L'AI non lo userà più come riferimento per le nuove risposte."
        confirmLabel="Elimina"
        destructive
        loading={deleteDocument.isPending}
        onConfirm={() => {
          if (!deleteId) return;
          deleteDocument.mutate(deleteId, {
            onSuccess: () => setDeleteId(null),
            onError: (err) => toast.error(err instanceof ApiError ? err.message : "Impossibile eliminare il documento"),
          });
        }}
      />
    </div>
  );
}
