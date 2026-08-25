import * as SelectPrimitive from "@radix-ui/react-select";
import { Check, ChevronDown } from "lucide-react";

export function Select({ value, onValueChange, options, label }) {
  return (
    <label className="grid gap-2 text-sm font-medium">
      {label}
      <SelectPrimitive.Root value={value} onValueChange={onValueChange}>
        <SelectPrimitive.Trigger className="flex w-full items-center justify-between rounded-lg border border-border bg-background px-3 py-2.5">
          <SelectPrimitive.Value />
          <SelectPrimitive.Icon>
            <ChevronDown size={16} />
          </SelectPrimitive.Icon>
        </SelectPrimitive.Trigger>
        <SelectPrimitive.Portal>
          <SelectPrimitive.Content className="z-50 overflow-hidden rounded-lg border border-border bg-popover p-1 shadow-xl">
            <SelectPrimitive.Viewport>
              {options.map((option) => (
                <SelectPrimitive.Item
                  key={option.id}
                  value={option.id}
                  disabled={option.disabled}
                  className="relative flex cursor-pointer select-none items-center rounded-md py-2 pl-8 pr-4 text-sm outline-none focus:bg-muted data-[disabled]:cursor-not-allowed data-[disabled]:opacity-45"
                >
                  <SelectPrimitive.ItemIndicator className="absolute left-2">
                    <Check size={14} />
                  </SelectPrimitive.ItemIndicator>
                  <SelectPrimitive.ItemText>
                    {option.label}
                  </SelectPrimitive.ItemText>
                </SelectPrimitive.Item>
              ))}
            </SelectPrimitive.Viewport>
          </SelectPrimitive.Content>
        </SelectPrimitive.Portal>
      </SelectPrimitive.Root>
    </label>
  );
}
