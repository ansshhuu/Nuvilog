import { cn } from '@/lib/utils'
import { STATUS_LABEL, STATUS_VAR, type Status } from '@/lib/status'

const SIZES = {
  xs: 'h-1.5 w-1.5',
  sm: 'h-2 w-2',
  md: 'h-2.5 w-2.5',
} as const

export interface StatusDotProps {
  status: Status
  size?: keyof typeof SIZES
  className?: string
}

/** A small solid circle. No border, no shadow — color only. */
export function StatusDot({ status, size = 'sm', className }: StatusDotProps) {
  return (
    <span
      role="img"
      aria-label={STATUS_LABEL[status]}
      className={cn('inline-block shrink-0 rounded-full', SIZES[size], className)}
      style={{ backgroundColor: STATUS_VAR[status] }}
    />
  )
}
