import { Bolt, CircleDot, Package, Zap, type LucideIcon } from 'lucide-react'

/**
 * Icon per category id. Shared between the ingest chips and the schema list
 * so a category reads as the same mark everywhere it appears. Falls back to
 * a neutral box for a category added to the registry later, rather than
 * crashing on a missing key.
 */
const CATEGORY_ICON: Record<string, LucideIcon> = {
  fasteners: Bolt,
  electrical: Zap,
  plumbing: CircleDot,
}

export function categoryIcon(categoryId: string): LucideIcon {
  return CATEGORY_ICON[categoryId] ?? Package
}
