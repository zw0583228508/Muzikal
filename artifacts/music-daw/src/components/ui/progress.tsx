import * as React from "react";
import { cn } from "@/lib/utils";

interface ProgressProps extends React.HTMLAttributes<HTMLDivElement> {
  value?: number;
  indicatorColor?: string;
}

const Progress = React.forwardRef<HTMLDivElement, ProgressProps>(
  ({ className, value = 0, indicatorColor = "bg-primary", ...props }, ref) => (
    <div
      ref={ref}
      className={cn("relative h-2 w-full overflow-hidden rounded-full bg-secondary shadow-inner", className)}
      {...props}
    >
      <div
        className={cn("h-full w-full flex-1 transition-all duration-500 ease-out shadow-[0_0_10px_currentColor]", indicatorColor)}
        style={{ transform: `translateX(-${100 - (value || 0)}%)` }}
      />
    </div>
  )
);
Progress.displayName = "Progress";

export { Progress };
