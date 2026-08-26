import { cva } from "class-variance-authority";
import { Slot } from "@radix-ui/react-slot";

import { cn } from "@/lib/utils";

const variants = cva(
  "inline-flex shrink-0 cursor-pointer items-center justify-center gap-2 whitespace-nowrap rounded-lg text-sm font-semibold transition disabled:pointer-events-none disabled:opacity-45 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring [&_svg]:pointer-events-none [&_svg]:shrink-0",
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
      size: {
        default: "h-10",
        sm: "h-8 rounded-md px-3 text-xs",
        lg: "h-12 px-5",
        icon: "h-9 w-9 p-0",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export function Button({ className, variant, size, asChild = false, ...props }) {
  const Component = asChild ? Slot : "button";
  return (
    <Component
      className={cn(variants({ variant, size }), className)}
      {...props}
    />
  );
}
