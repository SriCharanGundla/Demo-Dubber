import { cva } from "class-variance-authority";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium",
  {
    variants: {
      variant: {
        default: "border-transparent bg-muted text-muted-foreground",
        info: "border-blue-500/20 bg-blue-500/10 text-blue-700",
        success: "border-emerald-500/20 bg-emerald-500/10 text-emerald-700",
        warning: "border-amber-500/20 bg-amber-500/10 text-amber-800",
        destructive:
          "border-destructive/20 bg-destructive/10 text-destructive",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

export function Badge({ className, variant, ...props }) {
  return (
    <span
      className={cn(badgeVariants({ variant }), className)}
      {...props}
    />
  );
}
