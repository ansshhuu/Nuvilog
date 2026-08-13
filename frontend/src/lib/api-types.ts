/**
 * Wire shapes, mirrored 1:1 from the backend so responses can be consumed
 * without reshaping. See backend/main.py::get_product and
 * supabase/schema.sql (product_fields, validation_flags).
 */

/** product_fields.confidence_level */
export type ConfidenceLevel = 'high' | 'medium' | 'unverified'

/** product_fields.evidence_type */
export type EvidenceType = 'exact_match' | 'contextual_inference' | 'none'

/** validation_flags.issue_type */
export type IssueType = 'contradiction' | 'out_of_range' | 'missing_required'

export interface ProductFieldDTO {
  field_name: string
  value: string | null
  confidence_level: ConfidenceLevel | null
  evidence_type: EvidenceType | null
  source_snippet: string | null
  /** Phrase that implied a "medium" confidence value. */
  inference_chain: string | null
  is_ai_generated: boolean
}

/** One side of a contradiction: a value, where it was stated, and the line. */
export interface MentionDTO {
  value: string
  location: string
  /** The source line the value was read out of. Null when none was recorded. */
  snippet: string | null
}

export interface ValidationFlagDTO {
  field_name: string | null
  issue_type: IssueType
  message: string
  /**
   * One entry per conflicting value, in the order `message` names them.
   *
   * Three distinct states, and they mean different things:
   *   array  — stage 5's structured output; render the sides.
   *   []     — the finding has no sides (out_of_range).
   *   null   — written before validation_flags.mentions existed. Unknown, not
   *            empty: fall back to `message` and offer no per-side actions.
   */
  mentions: MentionDTO[] | null
}

/**
 * review_findings merges validation flags with stage 4's unverified fields,
 * so it carries one issue_type the flags table never stores.
 * See backend/main.py::_review_findings.
 */
export type FindingType = IssueType | 'unverified'

export interface ReviewFindingDTO {
  field_name: string | null
  issue_type: FindingType
  message: string
}

export interface ProductDTO {
  id: string
  category: string
  description: string | null
  raw_input_type: string
  raw_input_ref: string
  status: string
  created_at: string | null
  fields: ProductFieldDTO[]
  flags: ValidationFlagDTO[]
  review_findings: ReviewFindingDTO[]
}

/**
 * A row from GET /api/products. Identical to ProductDTO minus
 * `review_findings`, which the list endpoint does not compute — the list only
 * needs enough to derive each field's status for the density grid, and the
 * detail endpoint is what the review panel reads.
 * See backend/main.py::list_products.
 */
export type ProductSummaryDTO = Omit<ProductDTO, 'review_findings'>

export interface ProductListDTO {
  products: ProductSummaryDTO[]
  total: number
}

/**
 * The response both status transitions return —
 * POST /api/products/{id}/approve and .../mark-for-review.
 */
export interface StatusChangeDTO {
  id: string
  status: string
}

/** products.status values the UI can write. */
export const PRODUCT_STATUS = {
  approved: 'approved',
  needsReview: 'needs_review',
} as const

/**
 * What the ingest pipeline can actually read.
 * Mirrors backend/pipeline/types.py::InputType — note that XLSX is not in it.
 */
export type InputType = 'pdf' | 'csv' | 'text' | 'url'

/** File extensions the pipeline accepts, derived from InputType. */
export const ACCEPTED_EXTENSIONS = ['.pdf', '.csv'] as const

/** One entry of GET /api/categories, keyed by category id. */
export interface CategoryDTO {
  display_name: string
  description: string
  fields: unknown[]
}

export type CategoriesDTO = Record<string, CategoryDTO>

/** POST /api/ingest */
export interface IngestResultDTO {
  product_id: string
  category: string
  description: string | null
  enrichment_error: string | null
  raw_text_preview: string
  table_count: number
  fields: ProductFieldDTO[]
  flags: ValidationFlagDTO[]
  review_findings: ReviewFindingDTO[]
}

/** POST /api/ingest/batch */
export interface BatchIngestResultDTO {
  total: number
  succeeded: number
  failed: number
  concurrency: number
  product_ids: string[]
  results: unknown[]
}
