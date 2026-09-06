import { z } from "zod";

export const userStatusValues = ["active", "inactive", "suspended"] as const;

export const userFormSchema = z.object({
  name: z.string().min(1, "Il nome è obbligatorio").max(255),
  email: z.email({ message: "Inserisci un indirizzo email valido" }),
  company_name: z.string().max(255).optional().or(z.literal("")),
  status: z.enum(userStatusValues),
  notes: z.string().max(1000).optional().or(z.literal("")),
  group_ids: z.array(z.string()).optional(),
});

export type UserFormValues = z.infer<typeof userFormSchema>;

export const referralLinkFormSchema = z.object({
  referral_link: z
    .string()
    .max(1000)
    .refine((value) => value === "" || z.url().safeParse(value).success, {
      message: "Inserisci un URL valido (es. https://...)",
    }),
});

export type ReferralLinkFormValues = z.infer<typeof referralLinkFormSchema>;

// Deliberately smaller than the 1000 chars the backend column allows - this is
// meant as a short signature block (nome, telefono, email...), not free-form
// notes; see PERSONAL_CONTACTS_RESERVED_CHARS in lib/validation/campaigns.ts.
export const personalContactsFormSchema = z.object({
  personal_contacts: z.string().max(300),
});

export type PersonalContactsFormValues = z.infer<typeof personalContactsFormSchema>;

export const groupFormSchema = z.object({
  name: z.string().min(1, "Il nome è obbligatorio").max(100),
  description: z.string().max(500).optional().or(z.literal("")),
});

export type GroupFormValues = z.infer<typeof groupFormSchema>;
