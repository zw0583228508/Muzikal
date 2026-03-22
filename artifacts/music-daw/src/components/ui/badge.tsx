import * as React from "react"
import { cn } from "@/lib/utils"

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "default" | "secondary" | "destructive" | "outline" | "accent";
}

function Badge({ className, variant = "default", ...props }: BadgeProps) {
  return (
    <div
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
        {
          "border-transparent bg-primary text-primary-foreground shadow-[0_0_10px_rgba(0,240,255,0.2)]": variant === "default",
          "border-transparent bg-secondary text-secondary-foreground": variant === "secondary",
          "border-transparent bg-destructive text-destructive-foreground": variant === "destructive",
          "border-transparent bg-accent text-accent-foreground shadow-[0_0_10px_rgba(255,0,123,0.2)]": variant === "accent",
          "text-foreground border-white/20": variant === "outline",
        },
        className
      )}
      {...props}
    />
  )
}

export { Badge }
