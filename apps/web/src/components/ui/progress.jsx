import * as ProgressPrimitive from "@radix-ui/react-progress";

export function Progress({ value = 0 }) {
  return (
    <ProgressPrimitive.Root className="h-2 overflow-hidden rounded-full bg-muted">
      <ProgressPrimitive.Indicator
        className="h-full bg-primary transition-transform"
        style={{ transform: `translateX(-${100 - value}%)` }}
      />
    </ProgressPrimitive.Root>
  );
}
