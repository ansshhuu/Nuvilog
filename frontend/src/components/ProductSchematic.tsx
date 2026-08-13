import { cn } from '@/lib/utils'

export interface ProductSchematicProps {
  className?: string
}

/**
 * Line-art schematic shown beside the product title: a bolt in side elevation
 * and the matching hex profile end-on, the way a fastener would be drawn on a
 * spec sheet.
 *
 * Deliberately decorative and static — it illustrates the category, it is not
 * derived from the extracted dimensions, so it must never be read as a
 * to-scale drawing of this particular part. aria-hidden for that reason: it
 * carries no information a screen reader would need.
 *
 * Strokes use currentColor so the caller sets the tone with a text- class,
 * and stay non-scaling so the 1px line reads the same at any rendered size.
 */
export function ProductSchematic({ className }: ProductSchematicProps) {
  return (
    <div
      aria-hidden
      className={cn('flex shrink-0 items-center gap-3 text-text-muted', className)}
    >
      {/* Side elevation: hex head, shank, threaded shaft. */}
      <svg
        width="96"
        height="30"
        viewBox="0 0 96 30"
        fill="none"
        stroke="currentColor"
        strokeWidth="1"
        vectorEffect="non-scaling-stroke"
      >
        {/* Head */}
        <rect x="0.5" y="4.5" width="17" height="21" />
        {/* Chamfer lines across the head face */}
        <line x1="0.5" y1="10.5" x2="17.5" y2="10.5" />
        <line x1="0.5" y1="19.5" x2="17.5" y2="19.5" />
        {/* Unthreaded shank */}
        <rect x="17.5" y="10.5" width="12" height="9" />
        {/* Threaded shaft */}
        <rect x="29.5" y="10.5" width="60" height="9" />
        {/* Thread ticks — spaced wide enough to still read as individual
            lines at this size rather than blurring into a solid hatch. */}
        {Array.from({ length: 8 }, (_, i) => (
          <line
            key={i}
            x1={36 + i * 7}
            y1="10.5"
            x2={32.5 + i * 7}
            y2="19.5"
            opacity="0.75"
          />
        ))}
        {/* Centre line */}
        <line
          x1="0.5"
          y1="15"
          x2="95.5"
          y2="15"
          strokeDasharray="6 3 1 3"
          opacity="0.5"
        />
      </svg>

      {/* End-on: hex profile with the thread bore. */}
      <svg
        width="30"
        height="30"
        viewBox="0 0 30 30"
        fill="none"
        stroke="currentColor"
        strokeWidth="1"
        vectorEffect="non-scaling-stroke"
      >
        <polygon points="15,1.5 27,8.25 27,21.75 15,28.5 3,21.75 3,8.25" />
        <circle cx="15" cy="15" r="6.5" />
        <circle cx="15" cy="15" r="4.5" opacity="0.5" />
      </svg>
    </div>
  )
}
