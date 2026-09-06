import { CheckIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { WIZARD_STEPS } from "@/lib/validation/campaigns";

export function WizardStepper({ currentStep }: { currentStep: number }) {
  return (
    <ol className="flex flex-wrap items-center gap-x-2 gap-y-3">
      {WIZARD_STEPS.map((label, index) => {
        const stepNumber = index + 1;
        const isDone = stepNumber < currentStep;
        const isCurrent = stepNumber === currentStep;
        return (
          <li key={label} className="flex items-center gap-2">
            <div
              className={cn(
                "flex size-6 shrink-0 items-center justify-center rounded-full text-xs font-medium transition-all duration-300",
                isDone && "bg-brand-gradient text-primary-foreground",
                isCurrent && "glow-primary bg-primary/15 text-primary ring-2 ring-primary",
                !isDone && !isCurrent && "bg-muted text-muted-foreground"
              )}
            >
              {isDone ? <CheckIcon className="size-3.5" /> : stepNumber}
            </div>
            <span className={cn("text-sm", isCurrent ? "font-medium text-foreground" : "text-muted-foreground")}>
              {label}
            </span>
            {stepNumber < WIZARD_STEPS.length && (
              <span
                className={cn(
                  "mx-1 h-px w-6 transition-colors duration-500 sm:w-10",
                  isDone ? "bg-primary" : "bg-border"
                )}
              />
            )}
          </li>
        );
      })}
    </ol>
  );
}
