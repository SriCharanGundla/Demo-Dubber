import { Toaster as Sonner } from "sonner";

export function Toaster(props) {
  return (
    <Sonner
      closeButton
      richColors
      position="top-right"
      toastOptions={{
        classNames: {
          toast: "font-sans",
          title: "font-semibold",
          description: "text-muted-foreground",
        },
      }}
      {...props}
    />
  );
}
