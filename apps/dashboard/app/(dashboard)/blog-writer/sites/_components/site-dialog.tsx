"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useCreateWordpressSite, useUpdateWordpressSite } from "@/hooks/use-blog-writer";
import { ApiError } from "@/lib/api/errors";
import type { WordpressSiteResponse } from "@/types/api";

const STATUS_OPTIONS = [
  { value: "draft", label: "Bozza" },
  { value: "publish", label: "Pubblicato" },
  { value: "pending", label: "In revisione" },
  { value: "private", label: "Privato" },
];

interface SiteDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  site?: WordpressSiteResponse | null;
}

export function SiteDialog({ open, onOpenChange, site }: SiteDialogProps) {
  const isEdit = !!site;
  const createSite = useCreateWordpressSite();
  const updateSite = useUpdateWordpressSite();
  const isPending = createSite.isPending || updateSite.isPending;

  const [name, setName] = useState("");
  const [siteUrl, setSiteUrl] = useState("");
  const [apiUrl, setApiUrl] = useState("");
  const [username, setUsername] = useState("");
  const [applicationPassword, setApplicationPassword] = useState("");
  const [defaultStatus, setDefaultStatus] = useState("draft");
  const [language, setLanguage] = useState("it");

  useEffect(() => {
    if (!open) return;
    setName(site?.name ?? "");
    setSiteUrl(site?.site_url ?? "");
    setApiUrl(site?.api_url ?? "");
    setUsername(site?.username ?? "");
    setApplicationPassword("");
    setDefaultStatus(site?.default_status ?? "draft");
    setLanguage(site?.language ?? "it");
  }, [open, site]);

  function handleSubmit() {
    if (!name.trim() || !siteUrl.trim() || !apiUrl.trim() || !username.trim()) return;
    if (!isEdit && !applicationPassword.trim()) return;

    if (isEdit && site) {
      updateSite.mutate(
        {
          id: site.id,
          payload: {
            name: name.trim(),
            site_url: siteUrl.trim(),
            api_url: apiUrl.trim(),
            username: username.trim(),
            application_password: applicationPassword.trim() || undefined,
            default_status: defaultStatus,
            language: language.trim(),
          },
        },
        {
          onSuccess: () => {
            toast.success("Sito WordPress aggiornato");
            onOpenChange(false);
          },
          onError: (error) => toast.error(error instanceof ApiError ? error.detail : "Aggiornamento non riuscito"),
        }
      );
    } else {
      createSite.mutate(
        {
          name: name.trim(),
          site_url: siteUrl.trim(),
          api_url: apiUrl.trim(),
          username: username.trim(),
          application_password: applicationPassword.trim(),
          default_status: defaultStatus,
          language: language.trim(),
        },
        {
          onSuccess: () => {
            toast.success("Sito WordPress collegato");
            onOpenChange(false);
          },
          onError: (error) => toast.error(error instanceof ApiError ? error.detail : "Collegamento non riuscito"),
        }
      );
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{isEdit ? "Modifica sito WordPress" : "Connetti sito WordPress"}</DialogTitle>
          <DialogDescription>
            Usa una Application Password WordPress (Utenti → Profilo → Application Passwords sul sito), non la
            password dell&apos;account. Le credenziali vengono cifrate e non vengono mai mostrate di nuovo.
          </DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="space-y-2 sm:col-span-2">
            <Label htmlFor="site-name">Nome identificativo</Label>
            <Input id="site-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Blog aziendale" />
          </div>
          <div className="space-y-2">
            <Label htmlFor="site-url">URL del sito</Label>
            <Input id="site-url" value={siteUrl} onChange={(e) => setSiteUrl(e.target.value)} placeholder="https://tuosito.com" />
          </div>
          <div className="space-y-2">
            <Label htmlFor="site-api-url">URL API WordPress</Label>
            <Input
              id="site-api-url"
              value={apiUrl}
              onChange={(e) => setApiUrl(e.target.value)}
              placeholder="https://tuosito.com/wp-json"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="site-username">Username WordPress</Label>
            <Input id="site-username" value={username} onChange={(e) => setUsername(e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="site-password">
              Application Password {isEdit && "(lascia vuota per non modificarla)"}
            </Label>
            <Input
              id="site-password"
              type="password"
              autoComplete="off"
              value={applicationPassword}
              onChange={(e) => setApplicationPassword(e.target.value)}
              placeholder="xxxx xxxx xxxx xxxx xxxx xxxx"
            />
          </div>
          <div className="space-y-2">
            <Label>Stato pubblicazione predefinito</Label>
            <Select items={STATUS_OPTIONS} value={defaultStatus} onValueChange={(v) => setDefaultStatus(v ?? "draft")}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {STATUS_OPTIONS.map((o) => (
                  <SelectItem key={o.value} value={o.value}>
                    {o.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="site-language">Lingua principale</Label>
            <Input id="site-language" value={language} onChange={(e) => setLanguage(e.target.value)} placeholder="it" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Annulla
          </Button>
          <Button onClick={handleSubmit} disabled={isPending}>
            {isPending ? "Salvataggio..." : isEdit ? "Salva modifiche" : "Collega e testa"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
