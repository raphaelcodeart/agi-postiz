import { z } from "zod";

export const loginSchema = z.object({
  email: z.email({ message: "Inserisci un indirizzo email valido" }),
  password: z.string().min(1, { message: "La password è obbligatoria" }),
});

export type LoginFormValues = z.infer<typeof loginSchema>;
