import { cn } from "@/lib/utils";

export function Card({ className, ...props }) {
  return (
    <section
      className={cn(
        "rounded-2xl border border-border bg-card p-5 shadow-sm",
        className,
      )}
      {...props}
    />
  );
}
