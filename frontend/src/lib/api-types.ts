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

export interface ValidationFlagDTO {
  field_name: string | null
  issue_type: IssueType
  message: string
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
