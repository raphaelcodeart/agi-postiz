"use client";

import { useMemo, useRef, useState, type ChangeEvent, type KeyboardEvent, type ReactNode } from "react";
import { toast } from "sonner";
import {
  BookOpenIcon,
  Building2Icon,
  FileTextIcon,
  FlaskConicalIcon,
  FolderIcon,
  FolderOpenIcon,
  GlobeIcon,
  InboxIcon,
  Loader2Icon,
  MailIcon,
  MapPinIcon,
  PencilIcon,
  PhoneIcon,
  PlusIcon,
  RefreshCwIcon,
  SearchIcon,
  SparklesIcon,
  Trash2Icon,
  UploadIcon,
  WandSparklesIcon,
  XIcon,
} from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { EmptyState } from "@/components/shared/empty-state";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import {
  useCreateKnowledgeCompany,
  useCreateKnowledgeDocument,
  useDeleteKnowledgeCompany,
  useDeleteKnowledgeDocument,
  useFindKnowledgeDocuments,
  useKnowledgeCompanies,
  useKnowledgeDocuments,
  useKnowledgeStats,
  useMoveKnowledgeDocuments,
  useReindexKnowledgeBase,
  useSearchKnowledgeBase,
  useUpdateKnowledgeCompany,
  useUpdateKnowledgeDocument,
  useUploadKnowledgeFile,
} from "@/hooks/use-omnichannel";
import { useDebounce } from "@/hooks/use-debounce";
import { ApiError } from "@/lib/api/client";
import { formatDateTime } from "@/lib/format";
import * as omnichannelService from "@/services/omnichannel";
import type { OmniKnowledgeCompanyResponse, OmniKnowledgeDocumentResponse, OmniKnowledgeFindHit, OmniKnowledgeKind } from "@/types/api";

const ACCEPTED_FILES = ".pdf,.docx,.txt,.md,.csv,.xlsx";
// Cartelle speciali accanto agli id delle aziende.
const ALL = "__all__";
const NONE = "none";

// Stima grezza (circa 4 caratteri per token in italiano): serve solo a far
// vedere quanto pesa un'istruzione "sempre attiva", che viaggia in ogni richiesta.
function estimateTokens(text: string): number {
  return Math.ceil(text.length / 4);
}

function errorMessage(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.message : fallback;
}

// "" nei <select> = nessuna azienda (vale per tutte).
const toCompanyId = (value: string): string | null => (value && value !== NONE && value !== ALL ? value : null);

// Due modi di cercare nell'elenco: "rapida" filtra mentre si scrive (titolo,
// nome del file, parole esatte nel testo); "avanzata" parte con Invio e usa il
// motore del bot, cosi' trova anche i file che parlano dell'argomento con altre
// parole. La seconda costa un embedding a ricerca: per questo non e' a ogni tasto.
type SearchMode = "quick" | "deep";
const MIN_DEEP_QUERY = 2;

// Le stesse parole che il server usa per il nome del file: servono a
// evidenziare nei risultati perche' un file e' uscito.
function searchTerms(query: string): string[] {
  return (query.toLowerCase().match(/[\p{L}\p{N}]+/gu) ?? []).filter((t) => t.length >= 2).slice(0, 10);
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

const MATCH_LABELS: Record<string, string> = { nome: "nome del file", testo: "parole nel testo", significato: "significato (AI)" };

type EditorState = {
  id: string | null;
  kind: OmniKnowledgeKind;
  title: string;
  content: string;
  companyId: string;
  alwaysOn: boolean;
};

const emptyEditor = (kind: OmniKnowledgeKind, companyId: string): EditorState => ({ id: null, kind, title: "", content: "", companyId, alwaysOn: false });

function editorTitle(editor: EditorState | null): string {
  if (!editor) return "";
  if (editor.kind === "instruction") return editor.id ? "Modifica istruzione" : "Nuova istruzione";
  return editor.id ? "Modifica documento" : "Nuovo documento";
}

export default function OmnichannelKnowledgeBasePage() {
  const [folder, setFolder] = useState<string>(ALL);
  const [textFilter, setTextFilter] = useState("");
  const [searchMode, setSearchMode] = useState<SearchMode>("quick");
  // La ricerca avanzata confermata con Invio (puo' differire da cio' che c'e' nella casella).
  const [deepQuery, setDeepQuery] = useState("");
  const debouncedText = useDebounce(textFilter, 300);
  const deepActive = searchMode === "deep" && deepQuery.trim().length >= MIN_DEEP_QUERY;
  const scope = folder === ALL ? undefined : folder;

  const { data: companies, isLoading: companiesLoading } = useKnowledgeCompanies();
  const { data: documents, isLoading, isFetching } = useKnowledgeDocuments({ company: scope, q: searchMode === "quick" ? debouncedText : undefined });
  const find = useFindKnowledgeDocuments({ q: searchMode === "deep" ? deepQuery : "", company: scope });
  const { data: stats } = useKnowledgeStats();
  const createDocument = useCreateKnowledgeDocument();
  const updateDocument = useUpdateKnowledgeDocument();
  const deleteDocument = useDeleteKnowledgeDocument();
  const uploadFile = useUploadKnowledgeFile();
  const moveDocuments = useMoveKnowledgeDocuments();
  const reindex = useReindexKnowledgeBase();

  const [editor, setEditor] = useState<EditorState | null>(null);
  const [loadingEditorId, setLoadingEditorId] = useState<string | null>(null);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [companyDialog, setCompanyDialog] = useState<OmniKnowledgeCompanyResponse | "new" | null>(null);
  const [deleteCompany, setDeleteCompany] = useState<OmniKnowledgeCompanyResponse | null>(null);
  const [uploadTarget, setUploadTarget] = useState<string>(NONE);
  const [uploading, setUploading] = useState<{ done: number; total: number } | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const fileInput = useRef<HTMLInputElement>(null);

  const currentCompany = companies?.find((c) => c.id === folder) ?? null;
  const companyFolderId = currentCompany?.id ?? "";

  function openFolder(next: string) {
    setFolder(next);
    setSelected(new Set());
    // I file caricati finiscono nella cartella aperta; da "Tutte" vanno fra
    // quelli senza azienda, a meno di sceglierne una.
    setUploadTarget(next === ALL ? NONE : next);
  }

  function runDeepSearch() {
    if (textFilter.trim().length < MIN_DEEP_QUERY) {
      toast.error(`Scrivi almeno ${MIN_DEEP_QUERY} caratteri`);
      return;
    }
    setDeepQuery(textFilter);
  }

  function switchMode(mode: SearchMode) {
    setSearchMode(mode);
    // Passando ad "avanzata" con del testo gia' scritto si cerca subito.
    if (mode === "deep") setDeepQuery(textFilter);
  }

  function clearSearch() {
    setTextFilter("");
    setDeepQuery("");
  }

  function onSearchKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" && searchMode === "deep") {
      e.preventDefault();
      runDeepSearch();
    } else if (e.key === "Escape") {
      clearSearch();
    }
  }

  const docs = (documents ?? []).filter((d) => d.kind !== "instruction");
  const instructions = (documents ?? []).filter((d) => d.kind === "instruction");
  const foundDocs = (find.data?.hits ?? []).filter((h) => h.document.kind !== "instruction");
  const foundInstructions = (find.data?.hits ?? []).filter((h) => h.document.kind === "instruction");
  const highlightTerms = useMemo(() => (deepActive ? searchTerms(deepQuery) : []), [deepActive, deepQuery]);
  const stalledDocs = (documents ?? []).filter((d) => d.embedded_chunks < d.chunk_count && d.error_message);
  const pendingEmbeddings = stalledDocs.reduce((sum, d) => sum + d.chunk_count - d.embedded_chunks, 0);

  const totalItems = (stats?.documents ?? 0) + (stats?.instructions ?? 0);
  const inCompanies = (companies ?? []).reduce((sum, c) => sum + c.document_count + c.instruction_count, 0);

  async function handleFiles(fileList: FileList | File[]) {
    const files = Array.from(fileList);
    if (!files.length) return;
    setUploading({ done: 0, total: files.length });
    let ok = 0;
    // Uno alla volta: i PDF grandi richiedono qualche secondo di estrazione, e
    // un errore su un file non deve far perdere gli altri.
    for (const [index, file] of files.entries()) {
      try {
        await uploadFile.mutateAsync({ file, companyId: toCompanyId(uploadTarget) });
        ok += 1;
      } catch (err) {
        toast.error(errorMessage(err, `Impossibile caricare ${file.name}`), { duration: 10000 });
      }
      setUploading({ done: index + 1, total: files.length });
    }
    setUploading(null);
    if (fileInput.current) fileInput.current.value = "";
    const where = companies?.find((c) => c.id === uploadTarget)?.name;
    if (ok) toast.success(`${ok === 1 ? "File caricato" : `${ok} file caricati`}${where ? ` in ${where}` : ""}`);
  }

  async function openEditor(doc: OmniKnowledgeDocumentResponse) {
    // L'elenco porta solo l'inizio del testo: per modificarlo serve quello intero.
    setLoadingEditorId(doc.id);
    try {
      const full = await omnichannelService.getKnowledgeDocument(doc.id);
      setEditor({
        id: full.id,
        kind: full.kind,
        title: full.title,
        content: full.content_text ?? "",
        companyId: full.company_id ?? "",
        alwaysOn: full.always_on,
      });
    } catch (err) {
      toast.error(errorMessage(err, "Impossibile aprire il documento"));
    } finally {
      setLoadingEditorId(null);
    }
  }

  function handleSave() {
    if (!editor) return;
    if (!editor.title.trim() || !editor.content.trim()) {
      toast.error("Titolo e contenuto sono obbligatori");
      return;
    }
    const payload = {
      title: editor.title,
      content_text: editor.content,
      company_id: editor.companyId || null,
      kind: editor.kind,
      always_on: editor.kind === "instruction" && editor.alwaysOn,
    };
    const callbacks = {
      onSuccess: () => {
        toast.success(editor.kind === "instruction" ? "Istruzione salvata: il bot la usa da subito" : "Documento salvato");
        setEditor(null);
      },
      onError: (err: unknown) => toast.error(errorMessage(err, "Impossibile salvare")),
    };
    if (editor.id) updateDocument.mutate({ id: editor.id, payload }, callbacks);
    else createDocument.mutate({ ...payload, source_type: "manual" }, callbacks);
  }

  function toggleSelected(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function moveSelected(target: string) {
    const ids = Array.from(selected);
    const companyId = toCompanyId(target);
    moveDocuments.mutate(
      { ids, companyId },
      {
        onSuccess: () => {
          const name = companies?.find((c) => c.id === companyId)?.name;
          toast.success(`${ids.length === 1 ? "Documento spostato" : `${ids.length} documenti spostati`} ${name ? `in ${name}` : "fra quelli senza azienda"}`);
          setSelected(new Set());
        },
        onError: (err) => toast.error(errorMessage(err, "Impossibile spostare")),
      }
    );
  }

  const saving = createDocument.isPending || updateDocument.isPending;
  const folderTitle = currentCompany ? currentCompany.name : folder === NONE ? "Senza azienda" : "Tutte le aziende";
  const scopeLabel = currentCompany ? currentCompany.name : folder === NONE ? '"Senza azienda"' : "tutte le aziende";

  return (
    <div>
      <PageHeader
        title="Knowledge Base"
        description="Documenti, listini e istruzioni da cui il bot prende le risposte, ordinati per azienda. A ogni messaggio arrivano al modello solo i pezzi pertinenti, così il costo resta basso anche con molte informazioni."
      />

      <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatBox label="Aziende" value={companies ? companies.length : undefined} />
        <StatBox label="Documenti" value={stats?.documents} />
        <StatBox label="Istruzioni" value={stats?.instructions} hint={stats?.always_on_instructions ? `${stats.always_on_instructions} sempre attive` : undefined} />
        <StatBox
          label="Ricerca semantica"
          value={stats ? (stats.chunks ? `${Math.round((stats.embedded_chunks / stats.chunks) * 100)}%` : "—") : undefined}
          hint={stats ? `${stats.embedded_chunks}/${stats.chunks} blocchi indicizzati` : undefined}
        />
      </div>

      {pendingEmbeddings > 0 && !uploading && (
        <div className="mb-4 flex flex-col gap-2 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 sm:flex-row sm:items-center sm:justify-between dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100">
          <p>
            {pendingEmbeddings} blocchi non hanno ancora l&apos;indice semantico: per ora il bot li trova solo per parole.
            Il sistema riprova da solo ogni 10 minuti; se hai appena ricaricato il credito OpenAI puoi farlo subito.
          </p>
          <Button
            size="sm"
            variant="outline"
            disabled={reindex.isPending}
            onClick={() =>
              reindex.mutate(undefined, {
                onSuccess: () => toast.success("Indicizzazione completata"),
                onError: (err) => toast.error(errorMessage(err, "Indicizzazione non riuscita"), { duration: 10000 }),
              })
            }
          >
            {reindex.isPending ? <Loader2Icon className="animate-spin" /> : <RefreshCwIcon />} Indicizza ora
          </Button>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[260px_minmax(0,1fr)]">
        <CompanySidebar
          companies={companies}
          loading={companiesLoading}
          folder={folder}
          totalItems={totalItems}
          withoutCompany={Math.max(totalItems - inCompanies, 0)}
          onOpen={openFolder}
          onNew={() => setCompanyDialog("new")}
        />

        <div className="min-w-0 space-y-4">
          {currentCompany ? (
            <CompanyCard company={currentCompany} onEdit={() => setCompanyDialog(currentCompany)} onDelete={() => setDeleteCompany(currentCompany)} />
          ) : (
            <div className="flex items-center gap-2">
              {folder === NONE ? <InboxIcon className="size-5 text-muted-foreground" /> : <FolderOpenIcon className="size-5 text-muted-foreground" />}
              <div>
                <h2 className="text-base font-semibold">{folderTitle}</h2>
                <p className="text-xs text-muted-foreground">
                  {folder === NONE
                    ? "Informazioni e regole che valgono per tutte le aziende."
                    : "Tutti i documenti e le istruzioni. Scegli un'azienda a sinistra per vedere solo i suoi."}
                </p>
              </div>
            </div>
          )}

          <Tabs defaultValue="documents">
            <TabsList>
              <TabsTrigger value="documents">
                <FileTextIcon /> Documenti{deepActive ? (find.data ? ` (${foundDocs.length})` : "") : documents ? ` (${docs.length})` : ""}
              </TabsTrigger>
              <TabsTrigger value="instructions">
                <WandSparklesIcon /> Istruzioni{deepActive ? (find.data ? ` (${foundInstructions.length})` : "") : documents ? ` (${instructions.length})` : ""}
              </TabsTrigger>
              <TabsTrigger value="test"><FlaskConicalIcon /> Prova il bot</TabsTrigger>
            </TabsList>

            <div className="mt-4 space-y-2">
              <div className="flex flex-col gap-2 sm:flex-row">
                <div className="relative flex-1">
                  <SearchIcon className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    className="pr-9 pl-8"
                    value={textFilter}
                    onChange={(e) => setTextFilter(e.target.value)}
                    onKeyDown={onSearchKeyDown}
                    aria-label={searchMode === "quick" ? "Filtra l'elenco" : "Ricerca avanzata"}
                    placeholder={
                      searchMode === "quick"
                        ? `Filtra per titolo, file o parole nel testo in ${scopeLabel}...`
                        : `Nome di un file o argomento da cercare in ${scopeLabel}, poi Invio...`
                    }
                  />
                  {(isFetching && !isLoading) || find.isFetching ? (
                    <Loader2Icon className="absolute top-1/2 right-2.5 size-4 -translate-y-1/2 animate-spin text-muted-foreground" />
                  ) : textFilter ? (
                    <button
                      type="button"
                      onClick={clearSearch}
                      aria-label="Svuota la ricerca"
                      className="absolute top-1/2 right-1.5 flex size-6 -translate-y-1/2 items-center justify-center rounded text-muted-foreground hover:bg-muted hover:text-foreground"
                    >
                      <XIcon className="size-4" />
                    </button>
                  ) : null}
                </div>
                <div className="flex gap-2">
                  <div role="group" aria-label="Tipo di ricerca" className="inline-flex h-9 rounded-md border bg-background p-0.5">
                    <ModeButton active={searchMode === "quick"} onClick={() => switchMode("quick")} icon={SearchIcon} label="Rapida" />
                    <ModeButton active={searchMode === "deep"} onClick={() => switchMode("deep")} icon={SparklesIcon} label="Avanzata" />
                  </div>
                  {searchMode === "deep" && (
                    <Button className="h-9" onClick={runDeepSearch} disabled={find.isFetching || textFilter.trim().length < MIN_DEEP_QUERY}>
                      {find.isFetching ? <Loader2Icon className="animate-spin" /> : <SearchIcon />} Cerca
                    </Button>
                  )}
                </div>
              </div>
              <p className="text-xs text-muted-foreground">
                {searchMode === "quick"
                  ? "Filtra l'elenco mentre scrivi. Per trovare i file che parlano di un argomento, anche con parole diverse, passa ad Avanzata."
                  : "Trova i file per nome e quelli in cui si parla di quello che scrivi, anche con parole diverse: è lo stesso motore che usa il bot. Premi Invio o Cerca."}
              </p>
            </div>

            <TabsContent value="documents" className="mt-4 space-y-4">
              <div
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragOver(true);
                }}
                onDragLeave={() => setDragOver(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setDragOver(false);
                  void handleFiles(e.dataTransfer.files);
                }}
                className={`rounded-lg border-2 border-dashed p-5 transition-colors ${dragOver ? "border-primary bg-primary/5" : "border-border"}`}
              >
                <div className="flex flex-col gap-4 lg:flex-row lg:items-end">
                  <div className="flex-1">
                    <p className="text-sm font-medium">Carica file</p>
                    <p className="text-xs text-muted-foreground">
                      PDF, Word, Excel, CSV, TXT o Markdown, fino a 25 MB ciascuno. Puoi trascinarne più di uno insieme.
                      Per i listini usa Excel o CSV con una riga per prodotto: il bot ritrova il prodotto giusto con il suo prezzo.
                    </p>
                  </div>
                  <div className="space-y-1.5 lg:w-56">
                    <Label className="text-xs">Carica in</Label>
                    <CompanySelect companies={companies} value={uploadTarget} onChange={setUploadTarget} noneValue={NONE} />
                  </div>
                  <div className="flex gap-2">
                    <input ref={fileInput} type="file" multiple accept={ACCEPTED_FILES} className="hidden" onChange={(e) => e.target.files && void handleFiles(e.target.files)} />
                    <Button onClick={() => fileInput.current?.click()} disabled={!!uploading}>
                      {uploading ? <Loader2Icon className="animate-spin" /> : <UploadIcon />}
                      {uploading ? `Caricamento ${uploading.done}/${uploading.total}` : "Scegli file"}
                    </Button>
                    <Button variant="outline" onClick={() => setEditor(emptyEditor("document", toCompanyId(uploadTarget) ?? ""))}>
                      <PlusIcon /> Testo
                    </Button>
                  </div>
                </div>
              </div>

              {selected.size > 0 && (
                <SelectionBar
                  count={selected.size}
                  companies={companies}
                  moving={moveDocuments.isPending}
                  onMove={moveSelected}
                  onClear={() => setSelected(new Set())}
                />
              )}

              {deepActive ? (
                <FindResults
                  kind="document"
                  query={deepQuery}
                  hits={foundDocs}
                  loading={find.isLoading}
                  fetching={find.isFetching}
                  error={find.error}
                  warning={find.data?.warning ?? null}
                  terms={highlightTerms}
                  showCompany={folder === ALL}
                  selected={selected}
                  onToggle={toggleSelected}
                  openingId={loadingEditorId}
                  onEdit={(doc) => void openEditor(doc)}
                  onDelete={(doc) => setDeleteId(doc.id)}
                  onClear={clearSearch}
                />
              ) : isLoading ? (
                <ListSkeleton />
              ) : docs.length === 0 ? (
                <EmptyState
                  icon={BookOpenIcon}
                  title={debouncedText ? "Nessun documento trovato" : currentCompany ? `Nessun documento per ${currentCompany.name}` : "Nessun documento"}
                  description={
                    debouncedText
                      ? "Prova con altre parole o cerca in tutte le aziende."
                      : "Carica cataloghi, listini, FAQ, procedure o condizioni di vendita: il bot risponderà usando queste informazioni."
                  }
                />
              ) : (
                <div className="space-y-3">
                  {docs.map((doc) => (
                    <DocumentRow
                      key={doc.id}
                      doc={doc}
                      showCompany={folder === ALL}
                      selected={selected.has(doc.id)}
                      onToggle={() => toggleSelected(doc.id)}
                      opening={loadingEditorId === doc.id}
                      onEdit={() => void openEditor(doc)}
                      onDelete={() => setDeleteId(doc.id)}
                    />
                  ))}
                </div>
              )}
            </TabsContent>

            <TabsContent value="instructions" className="mt-4 space-y-4">
              <div className="flex flex-col gap-3 rounded-lg border bg-muted/30 p-4 sm:flex-row sm:items-center sm:justify-between">
                <div className="text-sm">
                  <p className="font-medium">Insegna al bot come comportarsi{currentCompany ? ` per ${currentCompany.name}` : ""}</p>
                  <p className="text-muted-foreground">
                    Una regola per istruzione: &quot;Se chiedono un preventivo, chiedi città e data&quot;, &quot;Non promettere mai tempi di consegna&quot;.
                    Di norma il bot la usa solo quando il messaggio è pertinente; quelle <strong>sempre attive</strong> viaggiano in ogni risposta, quindi tienile brevi.
                  </p>
                </div>
                <Button onClick={() => setEditor(emptyEditor("instruction", companyFolderId))} className="shrink-0">
                  <PlusIcon /> Nuova istruzione
                </Button>
              </div>

              {selected.size > 0 && (
                <SelectionBar
                  count={selected.size}
                  companies={companies}
                  moving={moveDocuments.isPending}
                  onMove={moveSelected}
                  onClear={() => setSelected(new Set())}
                />
              )}

              {deepActive ? (
                <FindResults
                  kind="instruction"
                  query={deepQuery}
                  hits={foundInstructions}
                  loading={find.isLoading}
                  fetching={find.isFetching}
                  error={find.error}
                  warning={find.data?.warning ?? null}
                  terms={highlightTerms}
                  showCompany={folder === ALL}
                  selected={selected}
                  onToggle={toggleSelected}
                  openingId={loadingEditorId}
                  onEdit={(doc) => void openEditor(doc)}
                  onDelete={(doc) => setDeleteId(doc.id)}
                  onClear={clearSearch}
                />
              ) : isLoading ? (
                <ListSkeleton />
              ) : instructions.length === 0 ? (
                <EmptyState
                  icon={WandSparklesIcon}
                  title="Nessuna istruzione"
                  description="Scrivi come vuoi che il bot risponda a certe domande: tono, cosa chiedere, cosa non dire mai."
                  action={<Button onClick={() => setEditor(emptyEditor("instruction", companyFolderId))}><PlusIcon /> Nuova istruzione</Button>}
                />
              ) : (
                <div className="space-y-3">
                  {instructions.map((doc) => (
                    <DocumentRow
                      key={doc.id}
                      doc={doc}
                      showCompany={folder === ALL}
                      selected={selected.has(doc.id)}
                      onToggle={() => toggleSelected(doc.id)}
                      opening={loadingEditorId === doc.id}
                      onEdit={() => void openEditor(doc)}
                      onDelete={() => setDeleteId(doc.id)}
                    />
                  ))}
                </div>
              )}
            </TabsContent>

            <TabsContent value="test" className="mt-4">
              <TestPanel key={folder} companies={companies} initialCompany={companyFolderId} />
            </TabsContent>
          </Tabs>
        </div>
      </div>

      <Dialog open={!!editor} onOpenChange={(open) => !open && setEditor(null)}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>{editorTitle(editor)}</DialogTitle>
            <DialogDescription>
              {editor?.kind === "instruction"
                ? "Scrivi la regola come la spiegheresti a un collega nuovo."
                : "Testo libero: FAQ, listino prezzi, procedure, policy aziendali..."}
            </DialogDescription>
          </DialogHeader>
          {editor && (
            <div className="space-y-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label>Titolo</Label>
                  <Input
                    value={editor.title}
                    onChange={(e) => setEditor({ ...editor, title: e.target.value })}
                    placeholder={editor.kind === "instruction" ? "Es. Richieste di preventivo" : "Es. Politica di reso"}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label>Azienda</Label>
                  <CompanySelect companies={companies} value={editor.companyId} onChange={(v) => setEditor({ ...editor, companyId: v })} noneValue="" />
                </div>
              </div>
              <div className="space-y-1.5">
                <Label>{editor.kind === "instruction" ? "Istruzione" : "Contenuto"}</Label>
                <Textarea
                  value={editor.content}
                  onChange={(e) => setEditor({ ...editor, content: e.target.value })}
                  rows={10}
                  className="field-sizing-fixed h-64 resize-y overflow-y-auto"
                  placeholder={
                    editor.kind === "instruction"
                      ? "Quando un cliente chiede un preventivo, chiedi sempre: città, data dell'evento e numero di persone. Non dare mai un prezzo finale: di' che un collega lo ricontatterà entro 24 ore."
                      : "Scrivi qui il contenuto..."
                  }
                />
                <p className="text-xs text-muted-foreground">
                  {editor.content.length.toLocaleString("it-IT")} caratteri · circa {estimateTokens(editor.content).toLocaleString("it-IT")} token
                </p>
              </div>
              {editor.kind === "instruction" && (
                <div className="flex items-start justify-between gap-4 rounded-lg border p-3">
                  <div className="text-sm">
                    <p className="font-medium">Sempre attiva</p>
                    <p className="text-muted-foreground">
                      Inclusa in ogni risposta, anche quando il messaggio non c&apos;entra. Usala per le regole generali (tono, cose da non dire mai).
                    </p>
                    {editor.alwaysOn && estimateTokens(editor.content) > 150 && (
                      <p className="mt-1 text-amber-700 dark:text-amber-400">
                        Aggiunge circa {estimateTokens(editor.content)} token a ogni risposta. Se riguarda un argomento specifico, lasciala non attiva: il bot la userà solo quando serve.
                      </p>
                    )}
                  </div>
                  <Switch checked={editor.alwaysOn} onCheckedChange={(v) => setEditor({ ...editor, alwaysOn: v })} />
                </div>
              )}
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditor(null)}>Annulla</Button>
            <Button onClick={handleSave} disabled={saving}>{saving && <Loader2Icon className="animate-spin" />} Salva</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {companyDialog && (
        <CompanyDialog
          company={companyDialog === "new" ? null : companyDialog}
          onClose={() => setCompanyDialog(null)}
          onCreated={(company) => openFolder(company.id)}
        />
      )}

      {deleteCompany && (
        <DeleteCompanyDialog
          company={deleteCompany}
          onClose={() => setDeleteCompany(null)}
          onDeleted={() => openFolder(ALL)}
        />
      )}

      <ConfirmDialog
        open={!!deleteId}
        onOpenChange={(open) => !open && setDeleteId(null)}
        title="Eliminare questo elemento?"
        description="Il bot non lo userà più nelle nuove risposte."
        confirmLabel="Elimina"
        destructive
        loading={deleteDocument.isPending}
        onConfirm={() => {
          if (!deleteId) return;
          deleteDocument.mutate(deleteId, {
            onSuccess: () => {
              setDeleteId(null);
              setSelected((prev) => {
                const next = new Set(prev);
                next.delete(deleteId);
                return next;
              });
            },
            onError: (err) => toast.error(errorMessage(err, "Impossibile eliminare")),
          });
        }}
      />
    </div>
  );
}

function StatBox({ label, value, hint }: { label: string; value: number | string | undefined; hint?: string }) {
  return (
    <div className="rounded-lg border p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      {value === undefined ? <Skeleton className="mt-1 h-6 w-10" /> : <p className="text-xl font-semibold">{value}</p>}
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

function ListSkeleton() {
  return (
    <div className="space-y-2">
      <Skeleton className="h-16" />
      <Skeleton className="h-16" />
    </div>
  );
}

function CompanySelect({
  companies,
  value,
  onChange,
  noneValue,
  allLabel = "Nessuna azienda (vale per tutte)",
}: {
  companies: OmniKnowledgeCompanyResponse[] | undefined;
  value: string;
  onChange: (value: string) => void;
  noneValue: string;
  allLabel?: string;
}) {
  return (
    <select className="h-9 w-full rounded-md border bg-background px-3 text-sm" value={value} onChange={(e) => onChange(e.target.value)} aria-label="Azienda">
      <option value={noneValue}>{allLabel}</option>
      {(companies ?? []).map((c) => (
        <option key={c.id} value={c.id}>{c.name}</option>
      ))}
    </select>
  );
}

function CompanySidebar({
  companies,
  loading,
  folder,
  totalItems,
  withoutCompany,
  onOpen,
  onNew,
}: {
  companies: OmniKnowledgeCompanyResponse[] | undefined;
  loading: boolean;
  folder: string;
  totalItems: number;
  withoutCompany: number;
  onOpen: (folder: string) => void;
  onNew: () => void;
}) {
  const [filter, setFilter] = useState("");
  const visible = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    return (companies ?? []).filter((c) => !needle || c.name.toLowerCase().includes(needle));
  }, [companies, filter]);

  return (
    <aside className="space-y-3 lg:sticky lg:top-4 lg:self-start">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold">Aziende</p>
        <Button size="sm" variant="outline" onClick={onNew}><PlusIcon /> Nuova</Button>
      </div>

      {/* Su schermo piccolo un elenco lungo di aziende spingerebbe giù i documenti: basta un menu. */}
      <select
        className="h-9 w-full rounded-md border bg-background px-3 text-sm lg:hidden"
        value={folder}
        onChange={(e) => onOpen(e.target.value)}
        aria-label="Cartella"
      >
        <option value={ALL}>Tutte le aziende ({totalItems})</option>
        <option value={NONE}>Senza azienda ({withoutCompany})</option>
        {(companies ?? []).map((c) => (
          <option key={c.id} value={c.id}>{c.name} ({c.document_count + c.instruction_count})</option>
        ))}
      </select>

      <div className="hidden space-y-1 lg:block">
        <FolderButton active={folder === ALL} icon={FolderOpenIcon} label="Tutte le aziende" count={totalItems} onClick={() => onOpen(ALL)} />
        <FolderButton active={folder === NONE} icon={InboxIcon} label="Senza azienda" count={withoutCompany} onClick={() => onOpen(NONE)} />

        <div className="my-2 border-t" />

        {(companies?.length ?? 0) > 8 && (
          <div className="relative mb-1">
            <SearchIcon className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input className="h-8 pl-8 text-sm" value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Cerca azienda..." />
          </div>
        )}

        {loading ? (
          <div className="space-y-1">
            <Skeleton className="h-8" />
            <Skeleton className="h-8" />
          </div>
        ) : !companies?.length ? (
          <div className="rounded-lg border border-dashed p-3 text-xs text-muted-foreground">
            Crea un&apos;azienda per tenere in ordine i suoi documenti: nome, contatti e descrizione finiscono anche nelle risposte del bot.
          </div>
        ) : (
          <div className="max-h-[60vh] space-y-1 overflow-y-auto pr-1">
            {visible.map((c) => (
              <FolderButton
                key={c.id}
                active={folder === c.id}
                icon={folder === c.id ? FolderOpenIcon : FolderIcon}
                label={c.name}
                count={c.document_count + c.instruction_count}
                onClick={() => onOpen(c.id)}
              />
            ))}
            {!visible.length && <p className="px-2 text-xs text-muted-foreground">Nessuna azienda trovata</p>}
          </div>
        )}
      </div>
    </aside>
  );
}

function FolderButton({
  active,
  icon: Icon,
  label,
  count,
  onClick,
}: {
  active: boolean;
  icon: typeof FolderIcon;
  label: string;
  count: number;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors ${active ? "bg-primary/10 font-medium text-primary" : "hover:bg-muted"}`}
    >
      <Icon className="size-4 shrink-0" />
      <span className="min-w-0 flex-1 truncate">{label}</span>
      <span className="text-xs text-muted-foreground tabular-nums">{count}</span>
    </button>
  );
}

function CompanyCard({ company, onEdit, onDelete }: { company: OmniKnowledgeCompanyResponse; onEdit: () => void; onDelete: () => void }) {
  const contacts = [
    { icon: PhoneIcon, value: company.phone },
    { icon: MailIcon, value: company.email },
    { icon: GlobeIcon, value: company.website },
    { icon: MapPinIcon, value: company.address },
  ].filter((c) => c.value);

  return (
    <div className="rounded-lg border p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Building2Icon className="size-5" />
          </div>
          <div className="min-w-0">
            <h2 className="truncate text-base font-semibold">{company.name}</h2>
            <p className="text-xs text-muted-foreground">
              {company.document_count} {company.document_count === 1 ? "documento" : "documenti"} · {company.instruction_count}{" "}
              {company.instruction_count === 1 ? "istruzione" : "istruzioni"}
            </p>
          </div>
        </div>
        <div className="flex shrink-0 gap-1">
          <Button size="sm" variant="outline" onClick={onEdit}><PencilIcon /> Modifica</Button>
          <Button size="icon-sm" variant="ghost" className="text-destructive hover:text-destructive" onClick={onDelete} aria-label="Elimina azienda"><Trash2Icon /></Button>
        </div>
      </div>
      {company.description && <p className="mt-3 line-clamp-3 text-sm whitespace-pre-line text-muted-foreground">{company.description}</p>}
      {contacts.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1">
          {contacts.map(({ icon: Icon, value }) => (
            <span key={value} className="inline-flex min-w-0 items-center gap-1.5 text-xs text-muted-foreground">
              <Icon className="size-3.5 shrink-0" /> <span className="truncate">{value}</span>
            </span>
          ))}
        </div>
      )}
      {!company.description && !contacts.length && (
        <p className="mt-3 text-xs text-muted-foreground">
          Aggiungi descrizione e contatti con &quot;Modifica&quot;: il bot li usa quando un cliente chiede chi siete, dove trovarvi o come contattarvi.
        </p>
      )}
    </div>
  );
}

type CompanyForm = { name: string; description: string; website: string; email: string; phone: string; address: string; notes: string };

function CompanyDialog({
  company,
  onClose,
  onCreated,
}: {
  company: OmniKnowledgeCompanyResponse | null;
  onClose: () => void;
  onCreated: (company: OmniKnowledgeCompanyResponse) => void;
}) {
  const createCompany = useCreateKnowledgeCompany();
  const updateCompany = useUpdateKnowledgeCompany();
  const [form, setForm] = useState<CompanyForm>({
    name: company?.name ?? "",
    description: company?.description ?? "",
    website: company?.website ?? "",
    email: company?.email ?? "",
    phone: company?.phone ?? "",
    address: company?.address ?? "",
    notes: company?.notes ?? "",
  });
  const saving = createCompany.isPending || updateCompany.isPending;
  const set = (key: keyof CompanyForm) => (e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setForm({ ...form, [key]: e.target.value });

  function save() {
    if (!form.name.trim()) {
      toast.error("Il nome dell'azienda è obbligatorio");
      return;
    }
    const onError = (err: unknown) => toast.error(errorMessage(err, "Impossibile salvare l'azienda"));
    if (company) {
      updateCompany.mutate(
        { id: company.id, payload: form },
        {
          onSuccess: () => {
            toast.success("Azienda aggiornata");
            onClose();
          },
          onError,
        }
      );
    } else {
      createCompany.mutate(form, {
        onSuccess: (created) => {
          toast.success(`Azienda ${created.name} creata: ora puoi caricare i suoi documenti`);
          onCreated(created);
          onClose();
        },
        onError,
      });
    }
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{company ? `Modifica ${company.name}` : "Nuova azienda"}</DialogTitle>
          <DialogDescription>
            L&apos;azienda fa da cartella per i suoi documenti. Descrizione e contatti diventano una scheda che il bot consulta quando serve,
            senza costi in più sulle altre risposte.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label>Nome *</Label>
            <Input value={form.name} onChange={set("name")} placeholder="Es. Bottega Rossi" autoFocus />
          </div>
          <div className="space-y-1.5">
            <Label>Chi è e cosa fa</Label>
            <Textarea
              value={form.description}
              onChange={set("description")}
              rows={4}
              className="field-sizing-fixed resize-y"
              placeholder="Es. Negozio di ceramiche artigianali a Firenze dal 1980. Vendiamo online e in negozio, spediamo in tutta Europa."
            />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label>Telefono</Label>
              <Input value={form.phone} onChange={set("phone")} placeholder="+39 055 123456" />
            </div>
            <div className="space-y-1.5">
              <Label>Email</Label>
              <Input value={form.email} onChange={set("email")} placeholder="info@azienda.it" type="email" />
            </div>
            <div className="space-y-1.5">
              <Label>Sito web</Label>
              <Input value={form.website} onChange={set("website")} placeholder="https://azienda.it" />
            </div>
            <div className="space-y-1.5">
              <Label>Indirizzo</Label>
              <Input value={form.address} onChange={set("address")} placeholder="Via Roma 1, Firenze" />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label>Note interne</Label>
            <Textarea value={form.notes} onChange={set("notes")} rows={2} className="field-sizing-fixed resize-y" placeholder="Referente, accordi, promemoria..." />
            <p className="text-xs text-muted-foreground">Solo per te: il bot non le vede.</p>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Annulla</Button>
          <Button onClick={save} disabled={saving}>{saving && <Loader2Icon className="animate-spin" />} {company ? "Salva" : "Crea azienda"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function DeleteCompanyDialog({ company, onClose, onDeleted }: { company: OmniKnowledgeCompanyResponse; onClose: () => void; onDeleted: () => void }) {
  const deleteCompany = useDeleteKnowledgeCompany();
  const items = company.document_count + company.instruction_count;
  const [pending, setPending] = useState<boolean | null>(null);

  function run(deleteDocuments: boolean) {
    setPending(deleteDocuments);
    deleteCompany.mutate(
      { id: company.id, deleteDocuments },
      {
        onSuccess: () => {
          toast.success(deleteDocuments ? `${company.name} eliminata con i suoi documenti` : `${company.name} eliminata: i documenti sono in "Senza azienda"`);
          onDeleted();
          onClose();
        },
        onError: (err) => {
          setPending(null);
          toast.error(errorMessage(err, "Impossibile eliminare l'azienda"));
        },
      }
    );
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Eliminare {company.name}?</DialogTitle>
          <DialogDescription>
            {items
              ? `Contiene ${items} ${items === 1 ? "elemento" : "elementi"} fra documenti e istruzioni. Puoi tenerli (finiscono in "Senza azienda" e valgono per tutte) oppure eliminarli insieme all'azienda.`
              : "L'azienda è vuota."}
          </DialogDescription>
        </DialogHeader>
        <DialogFooter className="flex-col gap-2 sm:flex-col">
          {items > 0 && (
            <Button variant="outline" onClick={() => run(false)} disabled={deleteCompany.isPending}>
              {pending === false && <Loader2Icon className="animate-spin" />} Elimina l&apos;azienda, tieni i documenti
            </Button>
          )}
          <Button variant="destructive" onClick={() => run(true)} disabled={deleteCompany.isPending}>
            {pending === true && <Loader2Icon className="animate-spin" />} {items ? `Elimina azienda e ${items} ${items === 1 ? "elemento" : "elementi"}` : "Elimina"}
          </Button>
          <Button variant="ghost" onClick={onClose}>Annulla</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function SelectionBar({
  count,
  companies,
  moving,
  onMove,
  onClear,
}: {
  count: number;
  companies: OmniKnowledgeCompanyResponse[] | undefined;
  moving: boolean;
  onMove: (target: string) => void;
  onClear: () => void;
}) {
  const [target, setTarget] = useState("");
  return (
    <div className="flex flex-col gap-2 rounded-lg border bg-muted/40 p-3 sm:flex-row sm:items-center">
      <p className="text-sm font-medium sm:flex-1">{count} {count === 1 ? "selezionato" : "selezionati"}</p>
      <div className="flex gap-2">
        <div className="min-w-0 flex-1 sm:w-56">
          <CompanySelect companies={companies} value={target} onChange={setTarget} noneValue="" allLabel="Senza azienda" />
        </div>
        <Button size="sm" className="h-9" onClick={() => onMove(target)} disabled={moving}>
          {moving ? <Loader2Icon className="animate-spin" /> : <FolderIcon />} Sposta
        </Button>
        <Button size="sm" variant="ghost" className="h-9" onClick={onClear}>Annulla</Button>
      </div>
    </div>
  );
}

function DocumentRow({
  doc,
  showCompany,
  selected,
  onToggle,
  opening,
  onEdit,
  onDelete,
  highlight,
  extra,
}: {
  doc: OmniKnowledgeDocumentResponse;
  showCompany: boolean;
  selected: boolean;
  onToggle: () => void;
  opening: boolean;
  onEdit: () => void;
  onDelete: () => void;
  // Parole da evidenziare in titolo e nome del file (ricerca avanzata).
  highlight?: string[];
  // Al posto dell'anteprima: i passaggi trovati dalla ricerca avanzata.
  extra?: ReactNode;
}) {
  const indexing = doc.embedded_chunks < doc.chunk_count && !doc.error_message;
  return (
    <div className={`rounded-lg border p-4 transition-colors ${selected ? "border-primary/50 bg-primary/5" : ""}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex min-w-0 items-start gap-3">
          <Checkbox className="mt-0.5" checked={selected} onCheckedChange={onToggle} aria-label={`Seleziona ${doc.title}`} />
          <div className="min-w-0 space-y-1">
            <p className="truncate text-sm font-medium"><Highlight text={doc.title} terms={highlight} /></p>
            <div className="flex flex-wrap items-center gap-1.5">
              {doc.kind === "instruction" ? (
                doc.always_on ? <Badge>Sempre attiva</Badge> : <Badge variant="secondary">Quando pertinente</Badge>
              ) : (
                <Badge variant="outline">{doc.source_type === "manual" ? "testo" : doc.source_type.toUpperCase()}</Badge>
              )}
              {showCompany && (doc.company ? <Badge variant="secondary">{doc.company}</Badge> : <Badge variant="outline">tutte le aziende</Badge>)}
              {doc.kind !== "instruction" && (
                <span className="text-xs text-muted-foreground">
                  {doc.chunk_count} {doc.chunk_count === 1 ? "blocco" : "blocchi"}
                  {doc.file_name && <> · <Highlight text={doc.file_name} terms={highlight} /></>}
                </span>
              )}
              {indexing && (
                <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                  <Loader2Icon className="size-3 animate-spin" /> indicizzazione {doc.embedded_chunks}/{doc.chunk_count}
                </span>
              )}
              <span className="text-xs text-muted-foreground">· {formatDateTime(doc.updated_at)}</span>
            </div>
          </div>
        </div>
        <div className="flex shrink-0">
          <Button size="icon-sm" variant="ghost" onClick={onEdit} disabled={opening} aria-label="Modifica">
            {opening ? <Loader2Icon className="animate-spin" /> : <PencilIcon />}
          </Button>
          <Button size="icon-sm" variant="ghost" className="text-destructive hover:text-destructive" onClick={onDelete} aria-label="Elimina"><Trash2Icon /></Button>
        </div>
      </div>
      {!extra && doc.preview && <p className="mt-2 line-clamp-3 pl-7 text-sm whitespace-pre-line text-muted-foreground">{doc.preview}</p>}
      {extra}
      {doc.error_message && <p className="mt-2 pl-7 text-xs text-amber-700 dark:text-amber-400">{doc.error_message}</p>}
    </div>
  );
}

function ModeButton({ active, onClick, icon: Icon, label }: { active: boolean; onClick: () => void; icon: typeof SearchIcon; label: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`inline-flex items-center gap-1.5 rounded px-2.5 text-sm transition-colors ${active ? "bg-primary text-primary-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"}`}
    >
      <Icon className="size-3.5" /> {label}
    </button>
  );
}

function Highlight({ text, terms }: { text: string; terms?: string[] }) {
  if (!terms?.length) return <>{text}</>;
  const pattern = new RegExp(`(${terms.map(escapeRegExp).join("|")})`, "giu");
  // split con un gruppo catturante: le posizioni dispari sono le parole trovate.
  return (
    <>
      {text.split(pattern).map((part, index) =>
        index % 2 === 1 ? (
          <mark key={index} className="rounded-sm bg-amber-200/70 px-0.5 text-inherit dark:bg-amber-400/30">{part}</mark>
        ) : (
          part
        )
      )}
    </>
  );
}

function FindResults({
  kind,
  query,
  hits,
  loading,
  fetching,
  error,
  warning,
  terms,
  showCompany,
  selected,
  onToggle,
  openingId,
  onEdit,
  onDelete,
  onClear,
}: {
  kind: OmniKnowledgeKind;
  query: string;
  hits: OmniKnowledgeFindHit[];
  loading: boolean;
  fetching: boolean;
  error: unknown;
  warning: string | null;
  terms: string[];
  showCompany: boolean;
  selected: Set<string>;
  onToggle: (id: string) => void;
  openingId: string | null;
  onEdit: (doc: OmniKnowledgeDocumentResponse) => void;
  onDelete: (doc: OmniKnowledgeDocumentResponse) => void;
  onClear: () => void;
}) {
  const noun = kind === "instruction" ? "istruzione" : "documento";
  const nounPlural = kind === "instruction" ? "istruzioni" : "documenti";

  if (loading) return <ListSkeleton />;
  if (error) {
    return (
      <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
        {errorMessage(error, "Ricerca non riuscita")}
      </div>
    );
  }
  if (!hits.length) {
    return (
      <EmptyState
        icon={SearchIcon}
        title={`Nessun ${noun} trovato per “${query.trim()}”`}
        description={`Prova con altre parole${showCompany ? "" : " o cerca in tutte le aziende"}. Un file appena caricato si trova per contenuto solo quando l'indicizzazione è finita.`}
        action={<Button variant="outline" onClick={onClear}><XIcon /> Mostra tutti i {nounPlural}</Button>}
      />
    );
  }

  return (
    <div className={`space-y-3 ${fetching ? "opacity-70 transition-opacity" : ""}`}>
      <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
        <p>
          <span className="font-medium">{hits.length} {hits.length === 1 ? noun : nounPlural}</span>{" "}
          <span className="text-muted-foreground">per “{query.trim()}” · prima quelli trovati per nome, poi per contenuto</span>
        </p>
        <Button size="sm" variant="ghost" onClick={onClear}><XIcon /> Chiudi ricerca</Button>
      </div>
      {warning && (
        <p className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100">{warning}</p>
      )}
      {hits.map((hit) => (
        <DocumentRow
          key={hit.document.id}
          doc={hit.document}
          showCompany={showCompany}
          selected={selected.has(hit.document.id)}
          onToggle={() => onToggle(hit.document.id)}
          opening={openingId === hit.document.id}
          onEdit={() => onEdit(hit.document)}
          onDelete={() => onDelete(hit.document)}
          highlight={terms}
          extra={<HitDetails hit={hit} terms={terms} />}
        />
      ))}
    </div>
  );
}

function HitDetails({ hit, terms }: { hit: OmniKnowledgeFindHit; terms: string[] }) {
  return (
    <div className="mt-2 space-y-2 pl-7">
      <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
        <span>Trovato per</span>
        {hit.matched_by.map((how) => (
          <Badge key={how} variant={how === "nome" ? "default" : "secondary"}>{MATCH_LABELS[how] ?? how}</Badge>
        ))}
      </div>
      {hit.snippets.map((snippet, index) => (
        <blockquote key={index} className="rounded-md border-l-2 border-primary/40 bg-muted/40 px-3 py-2">
          <p className="text-sm whitespace-pre-line text-muted-foreground"><Highlight text={snippet.content} terms={terms} /></p>
          {snippet.similarity != null && !snippet.matched_by.includes("testo") && (
            <p className="mt-1 text-[11px] text-muted-foreground">trovato per significato · somiglianza {Math.round(snippet.similarity * 100)}%</p>
          )}
        </blockquote>
      ))}
    </div>
  );
}

function TestPanel({ companies, initialCompany }: { companies: OmniKnowledgeCompanyResponse[] | undefined; initialCompany: string }) {
  const search = useSearchKnowledgeBase();
  const [question, setQuestion] = useState("");
  const [companyId, setCompanyId] = useState(initialCompany);
  const result = search.data;

  function run(generateReply: boolean) {
    if (!question.trim()) {
      toast.error("Scrivi una domanda di prova");
      return;
    }
    search.mutate(
      { query: question, generateReply, companyId: companyId || null },
      { onError: (err) => toast.error(errorMessage(err, "Prova non riuscita"), { duration: 10000 }) }
    );
  }

  return (
    <div className="space-y-4">
      <div className="space-y-3 rounded-lg border p-4">
        <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_220px]">
          <div className="space-y-1.5">
            <Label>Scrivi un messaggio come lo scriverebbe un cliente</Label>
            <Textarea value={question} onChange={(e) => setQuestion(e.target.value)} rows={3} placeholder="Es. Buongiorno, quanto costa la spedizione in Sardegna?" />
          </div>
          <div className="space-y-1.5">
            <Label>Cerca in</Label>
            <CompanySelect companies={companies} value={companyId} onChange={setCompanyId} noneValue="" allLabel="Tutte le aziende" />
            <p className="text-xs text-muted-foreground">Scegliendo un&apos;azienda il bot usa solo i suoi documenti più quelli generali.</p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={() => run(false)} disabled={search.isPending}>
            <SearchIcon /> Cosa trova il bot
          </Button>
          <Button onClick={() => run(true)} disabled={search.isPending}>
            {search.isPending ? <Loader2Icon className="animate-spin" /> : <SparklesIcon />} Genera risposta di prova
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">
          &quot;Cosa trova il bot&quot; mostra quali informazioni arriverebbero al modello, senza usare il modello di chat. &quot;Genera risposta&quot; fa una vera chiamata, con le stesse impostazioni delle bozze.
        </p>
      </div>

      {result && (
        <div className="space-y-4">
          {result.warning && (
            <p className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100">{result.warning}</p>
          )}

          {result.reply && (
            <div className="rounded-lg border border-primary/40 bg-primary/5 p-4">
              <p className="mb-1 text-xs font-medium text-muted-foreground">Risposta del bot</p>
              <p className="text-sm whitespace-pre-line">{result.reply}</p>
              {result.input_tokens != null && (
                <p className="mt-2 text-xs text-muted-foreground">{result.input_tokens} token in ingresso · {result.output_tokens} in uscita</p>
              )}
            </div>
          )}

          <div className="space-y-2">
            <p className="text-sm font-medium">
              {result.hits.length ? `Informazioni usate (${result.hits.length})` : "Nessuna informazione pertinente trovata"}
            </p>
            {!result.hits.length && (
              <p className="text-sm text-muted-foreground">
                Il bot risponderebbe solo con il prompt di sistema. Se la risposta dovrebbe stare nella knowledge base, controlla che il documento contenga davvero quelle informazioni.
              </p>
            )}
            {result.hits.map((hit, index) => (
              <div key={`${hit.document_id}-${index}`} className="rounded-lg border p-3">
                <div className="mb-1 flex flex-wrap items-center gap-1.5">
                  <span className="text-sm font-medium">{hit.document_title}</span>
                  {hit.kind === "instruction" && <Badge variant="secondary">istruzione</Badge>}
                  {hit.kind === "profile" && <Badge variant="secondary">scheda azienda</Badge>}
                  {hit.company && <Badge variant="outline">{hit.company}</Badge>}
                  <span className="text-xs text-muted-foreground">
                    trovato per {hit.matched_by.join(" e ")}
                    {hit.similarity != null ? ` · somiglianza ${Math.round(hit.similarity * 100)}%` : ""}
                  </span>
                </div>
                <p className="line-clamp-6 text-sm whitespace-pre-line text-muted-foreground">{hit.content}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
