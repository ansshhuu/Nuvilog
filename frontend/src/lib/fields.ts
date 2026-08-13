import type { Status } from './status'
import type { ProductFieldDTO, ValidationFlagDTO } from './api-types'

/**
 * A field as the review table renders it: the backend row plus the two things
 * the UI needs that no single column carries — the four-way status, and the
 * one-line reason shown under a non-verbatim status.
 */
export interface ReviewField {
  fieldName: string
  value: string | null
  status: Status
  /** Muted second line under the confidence label. Null for verbatim rows. */
  reason: string | null
  /** Human location of the evidence, e.g. "Page 1 - Table 1". */
  sourceLabel: string | null
  sourceSnippet: string | null
  field: ProductFieldDTO
  flags: ValidationFlagDTO[]
}

/**
 * The mockup's four statuses are a UI vocabulary; the backend stores three
 * confidence levels plus a separate validation_flags table. The mapping:
 *
 *   contradiction flag on the field  -> contradiction  (any confidence level)
 *   confidence_level "high"          -> verbatim
 *   confidence_level "medium"        -> inferred
 *   confidence_level "unverified"    -> unverified
 *
 * A contradiction outranks the confidence level because a field can be an
 * exact match against one page and be contradicted by another — the backend
 * makes the same call in _review_findings, which ranks flags above unverified
 * fields. Keeping the precedence identical here means the table and the
 * findings list can never disagree about a field's severity.
 *
 * A null confidence_level means the confidence engine has not scored the row
 * yet; it reads as unverified rather than being silently promoted.
 */
export function deriveStatus(
  field: ProductFieldDTO,
  flags: ValidationFlagDTO[],
): Status {
  if (flags.some((f) => f.issue_type === 'contradiction')) return 'contradiction'

  switch (field.confidence_level) {
    case 'high':
      return 'verbatim'
    case 'medium':
      return 'inferred'
    default:
      return 'unverified'
  }
}

function deriveReason(
  status: Status,
  field: ProductFieldDTO,
  flags: ValidationFlagDTO[],
): string | null {
  // Verbatim rows are self-explanatory — the mockup shows no second line.
  if (status === 'verbatim') return null

  if (status === 'contradiction') {
    const flag = flags.find((f) => f.issue_type === 'contradiction')
    return flag?.message ?? 'Conflicting values found'
  }

  if (status === 'inferred') {
    return field.inference_chain ?? 'Inferred from surrounding context'
  }

  // Unverified: prefer a flag's wording, else the backend's standing reason.
  const flag = flags.find((f) => f.issue_type !== 'contradiction')
  return flag?.message ?? 'No clear mention found'
}

export interface ToReviewFieldsOptions {
  /**
   * Resolves a field to a human source location ("Page 1 - Table 1").
   * Optional because the backend does not persist per-field page/table
   * coordinates — see the note in FieldReviewTable.
   */
  sourceLabelFor?: (field: ProductFieldDTO) => string | null
}

/** Joins fields to their validation flags and derives everything the UI shows. */
export function toReviewFields(
  fields: ProductFieldDTO[],
  flags: ValidationFlagDTO[],
  options: ToReviewFieldsOptions = {},
): ReviewField[] {
  return fields.map((field) => {
    const fieldFlags = flags.filter((f) => f.field_name === field.field_name)
    const status = deriveStatus(field, fieldFlags)

    return {
      fieldName: field.field_name,
      value: field.value,
      status,
      reason: deriveReason(status, field, fieldFlags),
      sourceLabel: options.sourceLabelFor?.(field) ?? null,
      sourceSnippet: field.source_snippet,
      field,
      flags: fieldFlags,
    }
  })
}

/** "Page 1 - Table 1" -> "the specification table" */
function locationPhrase(sourceLabel: string | null): string {
  const label = sourceLabel?.toLowerCase() ?? ''
  if (label.includes('table')) return 'the specification table'
  if (label.includes('note')) return 'a note on the source document'
  if (label.includes('text')) return 'a text block in the source document'
  return 'the source document'
}

/** "product_name" -> "product name" */
function readableFieldName(name: string): string {
  return name.replace(/_/g, ' ').toLowerCase()
}

/**
 * A one-line description of where a value came from, for the source panel's
 * CONTEXT block.
 *
 * Every clause is a fixed translation of something the pipeline recorded — the
 * derived status and the source location — in exactly the same spirit as the
 * status names and `confidenceRationale` below. It describes the evidence; it
 * never asserts anything about the part that the extraction did not determine,
 * and it deliberately does not paraphrase or embellish the snippet itself. The
 * verbatim `source_snippet` remains available via `sourceSnippet`, and the
 * matched row stays highlighted in the table above the block — which is what
 * "as shown above" refers to.
 */
export function sourceContext(field: ReviewField): string | null {
  const what = readableFieldName(field.fieldName)
  const where = locationPhrase(field.sourceLabel)

  switch (field.status) {
    case 'verbatim':
      return `The ${what} is explicitly listed in ${where} as shown above.`
    case 'inferred':
      return field.field.inference_chain
        ? `The ${what} is not stated directly. ${field.field.inference_chain}.`
        : `The ${what} is not stated directly in ${where}; it was inferred from the surrounding context.`
    case 'contradiction':
      return `Conflicting values for the ${what} appear in ${where}.`
    case 'unverified':
      return `No clear mention of the ${what} was found in ${where}.`
  }
}

/**
 * Why a confidence level was assigned, for the CONFIDENCE RATIONALE block.
 *
 * Every branch renders something the backend actually recorded:
 * `inference_chain` is written verbatim by the confidence engine, and the
 * remaining sentences are fixed translations of `evidence_type` — the same
 * kind of enum-to-label mapping as the status names, not invented reasoning.
 * Nothing here asserts anything the pipeline did not determine.
 */
export function confidenceRationale(field: ReviewField): string {
  if (field.status === 'contradiction') {
    const flag = field.flags.find((f) => f.issue_type === 'contradiction')
    return (
      flag?.message ??
      'Conflicting values for this field were found in the source.'
    )
  }

  switch (field.field.evidence_type) {
    case 'exact_match':
      return 'Exact string match found in source text.'
    case 'contextual_inference':
      return (
        field.field.inference_chain ??
        'Value appears in surrounding context, not as a direct statement.'
      )
    case 'none':
      return 'No support found anywhere in the source — AI-suggested, not fact.'
    default:
      return 'This field has not been scored by the confidence engine yet.'
  }
}

/** "thread_pitch" -> "THREAD PITCH" */
export function formatFieldName(name: string): string {
  return name.replace(/_/g, ' ').toUpperCase()
}
