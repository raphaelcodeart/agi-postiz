import { z } from "zod";

export const settingsFormSchema = z.object({
  global_concurrency_limit: z.number().int().min(1).max(100),
  concurrent_jobs_per_connection: z.number().int().min(1).max(20),
  pause_between_requests_seconds: z.number().int().min(0).max(120),
  max_publication_attempts: z.number().int().min(1).max(10),
  upload_max_size_bytes: z.number().int().min(1024 * 1024),
});

export type SettingsFormValues = z.infer<typeof settingsFormSchema>;
