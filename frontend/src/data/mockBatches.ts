import type { BatchSummary } from '@/components/BatchOverviewStrip'
import { buildStatuses, type StatusCounts } from './buildStatuses'

/**
 * Placeholder batch summaries. Replaced by GET /api/products data later —
 * shape matches BatchSummary so only the source swaps.
 */
function build(id: string, name: string, counts: StatusCounts): BatchSummary {
  return { id, name, fieldStatuses: buildStatuses(counts) }
}

export const MOCK_BATCHES: BatchSummary[] = [
  build('hxmb825250', 'HXMB825250', [10, 11, 4, 1]),
  build('screw_10x50', 'SCREW_10X50', [16, 7, 2, 1]),
  build('nut_m12', 'NUT_M12', [17, 5, 2, 1]),
  build('washer_12', 'WASHER_12', [17, 6, 1, 1]),
  build('bolt_m6x20', 'BOLT_M6X20', [14, 8, 2, 1]),
  build('anchor_8x40', 'ANCHOR_8X40', [11, 9, 4, 1]),
  build('rivet_4x10', 'RIVET_4X10', [15, 6, 3, 1]),
  build('pin_6x30', 'PIN_6X30', [18, 5, 1, 1]),
]
