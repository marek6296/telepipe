import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

// Tactile buttony z CinematicHero predlohy — vrstvené tiene sú v globals.css
const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap font-semibold transition-colors disabled:pointer-events-none disabled:opacity-50 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        gold: "btn-modern-light",
        dark: "btn-modern-dark",
        ghost: "btn-ghost-gold",
        outline:
          "rounded-full border border-[rgba(212,175,55,0.35)] text-[#e8c766] hover:bg-[rgba(212,175,55,0.08)]",
        danger:
          "rounded-full bg-[#3a1512] text-[#ff9b8f] border border-[#7a2b23] hover:bg-[#4a1a16]",
      },
      size: {
        sm: "h-9 px-4 text-sm",
        md: "h-11 px-6 text-sm",
        lg: "h-13 px-8 text-base",
        icon: "h-10 w-10 rounded-full",
      },
    },
    defaultVariants: { variant: "gold", size: "md" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

export function Button({ className, variant, size, ...props }: ButtonProps) {
  return (
    <button
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    />
  );
}

export { buttonVariants };
