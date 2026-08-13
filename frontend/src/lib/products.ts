import type { ProductDTO, ProductSummaryDTO } from './api-types'
import { deriveStatus } from './fields'
import type { Status } from './status'

/**
 * Turning stored products into what the two list views render.
 *
 * Everything here is derived from columns the backend actually returns. Where
 * the mockup showed something the database has no column for, it is left out
 * rather than filled with a plausible-looking value.
 */

/** The value of a field, if the product has one under that name. */
function fieldValue(
  product: ProductSummaryDTO | ProductDTO,
  name: string,
): string | null {
  return product.fields.find((f) => f.field_name === name)?.value ?? null
}

/**
 * The product's human name.
 *
 * `product_name` is the extracted field every schema in the registry defines,
 * so it is the name a reviewer recognises. It can legitimately be missing — a
 * document that never stated one — hence the fallbacks, which describe the
 * product rather than inventing a name for it.
 */
export function productDisplayName(
  product: ProductSummaryDTO | ProductDTO,
): string {
  return fieldValue(product, 'product_name') ?? `Untitled ${product.category}`
}

/**
 * Short display code for a product.
 *
 * Ids are server-generated uuids, which are too long to read in a list and
 * carry no meaning. The leading segment is enough to tell rows apart and to
 * match against a row in the Supabase table editor; the full id is still what
 * every request uses.
 */
export function productCode(product: ProductSummaryDTO | ProductDTO): string {
  return product.id.split('-')[0].toUpperCase()
}

/**
 * Where a product's values were read from.
 *
 * The backend stores one source per product (`raw_input_type` +
 * `raw_input_ref`) and does not persist per-field page or table coordinates —
 * so unlike the mockup's "Page 1 - Table 1", this is the document, not a
 * location inside it. Saying which document is true; inventing a page number
 * would not be.
 */
export function sourceDocumentLabel(product: ProductDTO): string {
  const { raw_input_type: type, raw_input_ref: ref } = product

  if (type === 'text') return 'Pasted text'
  if (type === 'url') return ref
  // pdf/csv are stored as a path on disk; only the filename is meaningful.
  const name = ref.split(/[/\\]/).pop() || ref
  return `${name} (${type})`
}

/** The four-way status of every field, for the density grids. */
export function fieldStatuses(product: ProductSummaryDTO): Status[] {
  return product.fields.map((field) =>
    deriveStatus(
      field,
      product.flags.filter((flag) => flag.field_name === field.field_name),
    ),
  )
}
