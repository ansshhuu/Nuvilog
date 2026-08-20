import {
  Bolt,
  CircleDot,
  Package,
  WashingMachine,
  Zap,
  type LucideIcon,
} from 'lucide-react'

/**
 * Icon per category id. Shared between the ingest chips and the schema list
 * so a category reads as the same mark everywhere it appears. Falls back to
 * a neutral box for a category added to the registry later, rather than
 * crashing on a missing key.
 *
 * lucide-react has no dedicated dishwasher glyph — WashingMachine is the
 * closest appliance shape in the set, used as a stand-in, not a claim that
 * it's a literal dishwasher icon.
 */
const CATEGORY_ICON: Record<string, LucideIcon> = {
  fasteners: Bolt,
  electrical: Zap,
  plumbing: CircleDot,
  dishwasher: WashingMachine,
}

export function categoryIcon(categoryId: string): LucideIcon {
  return CATEGORY_ICON[categoryId] ?? Package
}
