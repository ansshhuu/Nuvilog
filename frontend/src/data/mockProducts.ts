import type { ProductSummary } from '@/components/ProductList'
import { buildStatuses, type StatusCounts } from './buildStatuses'

/** Placeholder products — replaced by GET /api/products later. */
function build(id: string, name: string, counts: StatusCounts): ProductSummary {
  return { id, name, fieldStatuses: buildStatuses(counts) }
}

export const MOCK_PRODUCTS: ProductSummary[] = [
  build('HXMB825250', 'Hex Bolt M8 x 25mm', [10, 11, 4, 1]),
  build('SCREW_10X50', 'Socket Cap Screw M10 x 50mm', [16, 7, 2, 1]),
  build('NUT_M12', 'Hex Nut M12', [17, 5, 2, 1]),
  build('WASHER_12', 'Flat Washer 12mm', [17, 6, 1, 1]),
  build('BOLT_M6X20', 'Hex Bolt M6 x 20mm', [14, 8, 2, 1]),
  build('ANCHOR_8X40', 'Expansion Anchor 8x40mm', [11, 9, 4, 1]),
  build('RIVET_4X10', 'Blind Rivet 4x10mm', [15, 6, 3, 1]),
  build('PIN_6X30', 'Dowel Pin 6x30mm', [18, 5, 1, 1]),
  build('STUD_M10X60', 'Threaded Stud M10 x 60mm', [13, 8, 3, 1]),
  build('LOCKNUT_M8', 'Nylon Insert Lock Nut M8', [16, 6, 2, 1]),
  build('WASHER_08', 'Spring Washer 8mm', [15, 7, 2, 1]),
  build('SCREW_6X30', 'Pan Head Screw M6 x 30mm', [12, 9, 3, 1]),
  build('BOLT_M12X80', 'Hex Bolt M12 x 80mm', [14, 7, 4, 1]),
  build('NUT_M16', 'Hex Nut M16', [18, 4, 2, 1]),
  build('ANCHOR_10X50', 'Sleeve Anchor 10x50mm', [10, 10, 4, 2]),
  build('RIVET_5X12', 'Blind Rivet 5x12mm', [15, 6, 2, 1]),
  build('SCREW_4X16', 'Machine Screw M4 x 16mm', [17, 5, 1, 1]),
  build('BOLT_M20X100', 'Hex Bolt M20 x 100mm', [11, 9, 3, 2]),
  build('WASHER_16', 'Flat Washer 16mm', [19, 4, 1, 1]),
  build('PIN_8X40', 'Dowel Pin 8x40mm', [16, 6, 2, 1]),
  build('SCREW_12X60', 'Socket Cap Screw M12 x 60mm', [13, 8, 3, 1]),
  build('NUT_M6', 'Hex Nut M6', [18, 5, 1, 1]),
  build('BOLT_M8X40', 'Hex Bolt M8 x 40mm', [14, 8, 2, 2]),
]
