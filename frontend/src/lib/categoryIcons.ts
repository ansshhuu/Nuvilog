import { Package, WashingMachine, type LucideIcon } from 'lucide-react'

/**
 * Icon per category id. Falls back to a neutral box for a category added to
 * the registry later, rather than crashing on a missing key — the schema
 * list is dishwasher-only today (CategorySchemasView), but this stays a
 * lookup rather than a single hardcoded icon for that reason.
 *
 * lucide-react has no dedicated dishwasher glyph — WashingMachine is the
 * closest appliance shape in the set, used as a stand-in, not a claim that
 * it's a literal dishwasher icon.
 */
const CATEGORY_ICON: Record<string, LucideIcon> = {
  dishwasher: WashingMachine,
}

export function categoryIcon(categoryId: string): LucideIcon {
  return CATEGORY_ICON[categoryId] ?? Package
}
