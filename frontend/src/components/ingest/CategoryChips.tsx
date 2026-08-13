import { Bolt, CircleDot, Package, Zap } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

import { cn } from '@/lib/utils'
import { SkeletonBar } from '@/components/Feedback'

export interface CategoryOption {
  id: string
  displayName: string
}

export interface CategoryChipsProps {
  categories: CategoryOption[]
  selectedId: string | null
  onSelect: (id: string) => void
  loading?: boolean
  className?: string
}

/**
 * Icon per category id. Falls back to a neutral mark, so a category added to
 * the registry later still renders rather than crashing on a missing key.
 */
const CATEGORY_ICON: Record<string, LucideIcon> = {
  fasteners: Bolt,
  electrical: Zap,
  plumbing: CircleDot,
}

export function CategoryChips({
  categories,
  selectedId,
  onSelect,
  loading = false,
  className,
}: CategoryChipsProps) {
  if (loading) {
    return (
      <div className={cn('flex gap-3', className)} aria-busy="true">
        {Array.from({ length: 3 }, (_, i) => (
          <div
            key={i}
            className="flex flex-1 items-center gap-3 border border-border bg-surface px-4 py-3"
          >
            <SkeletonBar className="h-4 w-4 shrink-0" />
            <SkeletonBar className="w-2/3" />
          </div>
        ))}
      </div>
    )
  }

  return (
    <div className={cn('flex flex-wrap gap-3', className)}>
      {categories.map(({ id, displayName }) => {
        const Icon = CATEGORY_ICON[id] ?? Package
        const isSelected = id === selectedId
        return (
          <button
            key={id}
            type="button"
            aria-pressed={isSelected}
            onClick={() => onSelect(id)}
            className={cn(
              'flex min-w-[140px] flex-1 items-center gap-3 border px-4 py-3 text-left transition-colors',
              isSelected
                ? 'border-accent bg-accent/5 text-accent'
                : 'border-border bg-surface text-text-primary hover:border-text-muted',
            )}
          >
            <Icon size={15} strokeWidth={1.75} className="shrink-0" />
            <span className="truncate font-sans text-2xs uppercase tracking-[0.14em]">
              {displayName}
            </span>
          </button>
        )
      })}
    </div>
  )
}
