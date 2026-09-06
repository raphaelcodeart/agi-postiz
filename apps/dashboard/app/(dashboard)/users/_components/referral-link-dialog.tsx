"use client";

import { useEffect } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
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
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { referralLinkFormSchema, type ReferralLinkFormValues } from "@/lib/validation/users";
import { useUpdateUser } from "@/hooks/use-users";
import type { UserResponse } from "@/types/api";
import { ApiError } from "@/lib/api/errors";

interface ReferralLinkDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  user: UserResponse;
}

/**
 * Sets the personal referral/promoter link used by campaigns when "Includi
 * link referral" is acceso in fase di creazione (vedi campaign_resolver.py) -
 * ogni utente ha il proprio link, mai condiviso/mischiato con altri utenti,
 * perché il backend lo risolve per canale a partire dal suo proprietario reale.
 */
export function ReferralLinkDialog({ open, onOpenChange, user }: ReferralLinkDialogProps) {
  const updateUser = useUpdateUser(user.id);

  const form = useForm<ReferralLinkFormValues>({
    resolver: zodResolver(referralLinkFormSchema),
    defaultValues: { referral_link: user.referral_link ?? "" },
  });

  useEffect(() => {
    if (open) {
      form.reset({ referral_link: user.referral_link ?? "" });
    }
  }, [open, user, form]);

  function onSubmit(values: ReferralLinkFormValues) {
    updateUser.mutate(
      { referral_link: values.referral_link || null },
      {
        onSuccess: () => {
          toast.success(values.referral_link ? "Link referral salvato" : "Link referral rimosso");
          onOpenChange(false);
        },
        onError: (error) => {
          toast.error(error instanceof ApiError ? error.detail : "Operazione non riuscita");
        },
      }
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Link referral di {user.name}</DialogTitle>
          <DialogDescription>
            Se impostato, e se nella campagna è attiva l&apos;opzione &quot;Includi link referral&quot;, questo
            link viene aggiunto automaticamente al testo pubblicato su ogni canale social di {user.name} — solo
            i suoi, mai su canali di altri utenti. Lascia vuoto per non aggiungere nulla.
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="referral_link"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>URL personale</FormLabel>
                  <FormControl>
                    <Input placeholder="https://esempio.com/iscriviti/mario" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Annulla
              </Button>
              <Button type="submit" disabled={updateUser.isPending}>
                {updateUser.isPending ? "Salvataggio..." : "Salva"}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
