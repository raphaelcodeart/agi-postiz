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
import { Textarea } from "@/components/ui/textarea";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { groupFormSchema, type GroupFormValues } from "@/lib/validation/users";
import { useCreateGroup, useUpdateGroup } from "@/hooks/use-users";
import type { GroupResponse } from "@/types/api";
import { ApiError } from "@/lib/api/errors";

interface GroupFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  group?: GroupResponse;
}

export function GroupFormDialog({ open, onOpenChange, group }: GroupFormDialogProps) {
  const isEdit = !!group;
  const createGroup = useCreateGroup();
  const updateGroup = useUpdateGroup();
  const isSaving = createGroup.isPending || updateGroup.isPending;

  const form = useForm<GroupFormValues>({
    resolver: zodResolver(groupFormSchema),
    defaultValues: { name: "", description: "" },
  });

  useEffect(() => {
    if (open) {
      form.reset({
        name: group?.name ?? "",
        description: group?.description ?? "",
      });
    }
  }, [open, group, form]);

  function onSubmit(values: GroupFormValues) {
    const payload = { name: values.name, description: values.description || null };

    const onSuccess = () => {
      toast.success(isEdit ? "Gruppo aggiornato" : "Gruppo creato");
      onOpenChange(false);
    };
    const onError = (error: unknown) => {
      toast.error(error instanceof ApiError ? error.detail : "Operazione non riuscita");
    };

    if (isEdit) {
      updateGroup.mutate({ groupId: group.id, payload }, { onSuccess, onError });
    } else {
      createGroup.mutate(payload, { onSuccess, onError });
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{isEdit ? "Modifica gruppo" : "Nuovo gruppo"}</DialogTitle>
          <DialogDescription>
            {isEdit
              ? "Aggiorna nome e descrizione del gruppo."
              : "I gruppi permettono di indirizzare le campagne a insiemi di utenti."}
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Nome</FormLabel>
                  <FormControl>
                    <Input {...field} />
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
                  <FormLabel>Descrizione</FormLabel>
                  <FormControl>
                    <Textarea rows={2} {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Annulla
              </Button>
              <Button type="submit" disabled={isSaving}>
                {isSaving ? "Salvataggio..." : isEdit ? "Salva modifiche" : "Crea gruppo"}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
