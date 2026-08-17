import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Spája Tailwind triedy s korektným prepisovaním konfliktov. */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
