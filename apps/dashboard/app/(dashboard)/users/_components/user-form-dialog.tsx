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
import { Checkbox } from "@/components/ui/checkbox";
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
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { userFormSchema, type UserFormValues } from "@/lib/validation/users";
import { useCreateUser, useUpdateUser, useGroups } from "@/hooks/use-users";
import type { UserResponse } from "@/types/api";
import { ApiError } from "@/lib/api/errors";

interface UserFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  user?: UserResponse;
}

export function UserFormDialog({ open, onOpenChange, user }: UserFormDialogProps) {
  const isEdit = !!user;
  const groups = useGroups();
  const createUser = useCreateUser();
  const updateUser = useUpdateUser(user?.id ?? "");
  const isSaving = createUser.isPending || updateUser.isPending;

  const form = useForm<UserFormValues>({
    resolver: zodResolver(userFormSchema),
    defaultValues: {
      name: "",
      email: "",
      company_name: "",
      status: "active",
      notes: "",
      group_ids: [],
    },
  });

  useEffect(() => {
    if (open) {
      form.reset({
        name: user?.name ?? "",
        email: user?.email ?? "",
        company_name: user?.company_name ?? "",
        status: user?.status ?? "active",
        notes: user?.notes ?? "",
        group_ids: user?.groups.map((g) => g.id) ?? [],
      });
    }
  }, [open, user, form]);

  function onSubmit(values: UserFormValues) {
    const payload = {
      name: values.name,
      email: values.email,
      company_name: values.company_name || null,
      status: values.status,
      notes: values.notes || null,
      group_ids: values.group_ids ?? [],
    };

    const mutation = isEdit ? updateUser : createUser;
    mutation.mutate(payload as never, {
      onSuccess: () => {
        toast.success(isEdit ? "Utente aggiornato" : "Utente creato");
        onOpenChange(false);
      },
      onError: (error) => {
        toast.error(error instanceof ApiError ? error.detail : "Operazione non riuscita");
      },
    });
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{isEdit ? "Modifica utente" : "Nuovo utente"}</DialogTitle>
          <DialogDescription>
            {isEdit ? "Aggiorna i dati del cliente." : "Crea un nuovo cliente della piattaforma."}
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
              name="email"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Email</FormLabel>
                  <FormControl>
                    <Input type="email" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="company_name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Azienda</FormLabel>
                  <FormControl>
                    <Input {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="status"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Stato</FormLabel>
                  <Select
                    items={[
                      { value: "active", label: "Attivo" },
                      { value: "inactive", label: "Inattivo" },
                      { value: "suspended", label: "Sospeso" },
                    ]}
                    value={field.value}
                    onValueChange={field.onChange}
                  >
                    <FormControl>
                      <SelectTrigger className="w-full">
                        <SelectValue />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      <SelectItem value="active">Attivo</SelectItem>
                      <SelectItem value="inactive">Inattivo</SelectItem>
                      <SelectItem value="suspended">Sospeso</SelectItem>
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="notes"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Note</FormLabel>
                  <FormControl>
                    <Textarea rows={2} {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="group_ids"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Gruppi</FormLabel>
                  <div className="flex flex-wrap gap-3 rounded-md border p-3">
                    {groups.data && groups.data.length > 0 ? (
                      groups.data.map((group) => {
                        const checked = field.value?.includes(group.id) ?? false;
                        return (
                          <label key={group.id} className="flex items-center gap-2 text-sm">
                            <Checkbox
                              checked={checked}
                              onCheckedChange={(value) => {
                                const current = field.value ?? [];
                                field.onChange(
                                  value ? [...current, group.id] : current.filter((id) => id !== group.id)
                                );
                              }}
                            />
                            {group.name}
                          </label>
                        );
                      })
                    ) : (
                      <p className="text-sm text-muted-foreground">Nessun gruppo disponibile.</p>
                    )}
                  </div>
                </FormItem>
              )}
            />
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Annulla
              </Button>
              <Button type="submit" disabled={isSaving}>
                {isSaving ? "Salvataggio..." : isEdit ? "Salva modifiche" : "Crea utente"}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
