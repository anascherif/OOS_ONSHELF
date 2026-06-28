/*
  Just the cn() helper — merges Tailwind classes without conflicts.
  If you add more utilities, keep them here rather than scattered.
*/

import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
