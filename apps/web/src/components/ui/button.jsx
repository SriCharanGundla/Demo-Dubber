import { cva } from "class-variance-authority";

import { cn } from "@/lib/utils";

const variants = cva(
  "inline-flex cursor-pointer items-center justify-center gap-2 rounded-lg text-sm font-semibold transition disabled:pointer-events-none disabled:opacity-45 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
  {
    variants: {
      variant: {
        default:
          "bg-primary px-4 py-2.5 text-primary-foreground hover:brightness-110",
        outline:
          "border border-border bg-transparent px-4 py-2.5 hover:bg-muted",
        ghost: "px-3 py-2 hover:bg-muted",
        destructive:
          "bg-destructive px-4 py-2.5 text-white hover:brightness-110",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

export function Button({ className, variant, ...props }) {
  return <button className={cn(variants({ variant }), className)} {...props} />;
}
