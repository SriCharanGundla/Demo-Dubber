import * as ProgressPrimitive from "@radix-ui/react-progress";

export function Progress({ value = 0, variant = "default" }) {
  return (
    <ProgressPrimitive.Root
      className="h-2 overflow-hidden rounded-full bg-muted"
      value={value}
    >
      <ProgressPrimitive.Indicator
        className={`h-full transition-transform ${variant === "destructive" ? "bg-destructive" : "bg-primary"}`}
        style={{ transform: `translateX(-${100 - value}%)` }}
      />
    </ProgressPrimitive.Root>
  );
}
