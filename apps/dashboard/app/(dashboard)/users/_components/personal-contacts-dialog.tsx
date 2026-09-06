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
import { Textarea } from "@/components/ui/textarea";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormDescription,
  FormMessage,
} from "@/components/ui/form";
import { personalContactsFormSchema, type PersonalContactsFormValues } from "@/lib/validation/users";
import { useUpdateUser } from "@/hooks/use-users";
import type { UserResponse } from "@/types/api";
import { ApiError } from "@/lib/api/errors";

interface PersonalContactsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  user: UserResponse;
}

/**
 * Sets the personal contacts/signature block used by campaigns when "Includi
 * contatti personali" e' acceso in fase di creazione (vedi campaign_resolver.py)
 * - ogni utente ha il proprio blocco, mai condiviso/mischiato con altri utenti,
 * appeso subito dopo l'eventuale link referral, stessa logica del link stesso.
 */
export function PersonalContactsDialog({ open, onOpenChange, user }: PersonalContactsDialogProps) {
  const updateUser = useUpdateUser(user.id);

  const form = useForm<PersonalContactsFormValues>({
    resolver: zodResolver(personalContactsFormSchema),
    defaultValues: { personal_contacts: user.personal_contacts ?? "" },
  });

  useEffect(() => {
    if (open) {
      form.reset({ personal_contacts: user.personal_contacts ?? "" });
    }
  }, [open, user, form]);

  function onSubmit(values: PersonalContactsFormValues) {
    updateUser.mutate(
      { personal_contacts: values.personal_contacts || null },
      {
        onSuccess: () => {
          toast.success(values.personal_contacts ? "Contatti personali salvati" : "Contatti personali rimossi");
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
          <DialogTitle>Contatti personali di {user.name}</DialogTitle>
          <DialogDescription>
            Se impostato, e se nella campagna è attiva l&apos;opzione &quot;Includi contatti personali&quot;,
            questo blocco di testo viene aggiunto automaticamente in fondo al testo pubblicato su ogni canale
            social di {user.name} — subito dopo l&apos;eventuale link referral — solo i suoi, mai su canali di
            altri utenti. Lascia vuoto per non aggiungere nulla.
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="personal_contacts"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Firma / contatti</FormLabel>
                  <FormControl>
                    <Textarea
                      rows={4}
                      placeholder={"Mario Rossi\nTel. 333 1234567\nmario@esempio.com"}
                      {...field}
                    />
                  </FormControl>
                  <FormDescription>{(field.value ?? "").length}/300 caratteri</FormDescription>
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
