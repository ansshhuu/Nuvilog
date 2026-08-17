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

/** backend/pipeline/schema_registry.py::FieldDef.type */
export type SchemaFieldType =
  | 'string'
  | 'integer'
  | 'number'
  | 'dimension'
  | 'boolean'

/** backend/pipeline/schema_registry.py::ValidRange */
export interface ValidRangeDTO {
  min: number | null
  max: number | null
}

/** backend/pipeline/schema_registry.py::FieldDef, as returned in CategoryDTO.fields. */
export interface SchemaFieldDTO {
  name: string
  type: SchemaFieldType
  required: boolean
  description: string
  unit: string | null
  valid_range: ValidRangeDTO | null
}

/** One entry of GET /api/categories, keyed by category id. */
export interface CategoryDTO {
  display_name: string
  description: string
  fields: SchemaFieldDTO[]
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

// ---------------------------------------------------------------------------
// GET /api/evaluation-report
// ---------------------------------------------------------------------------

/** A {score, total} pair for one evaluation tier. */
export interface TierScoreDTO {
  score: number
  total: number
}

/** Tier 3 carries an extra fabrication-violation count. */
export interface Tier3ScoreDTO extends TierScoreDTO {
  fabrication_violations: number
}

/** Per-row evaluation data from step6_7_report.json. */
export interface EvalRowDTO {
  mpn: string
  is_known: boolean
  /** Null when is_known=false (no ground truth, Tier 1 is N/A). */
  tier1: TierScoreDTO | null
  tier2: TierScoreDTO
  tier3: Tier3ScoreDTO
}

/** Before/after value pair for one comparison metric. Values are "X/Y" strings. */
export interface ComparisonBeforeAfterDTO {
  baseline: string
  enriched: string
}

/** Step 8 before/after comparison for one MPN. Keyed by MPN in the API response. */
export interface ComparisonRowDTO {
  descriptions_nonempty: ComparisonBeforeAfterDTO
  attributes_verified: ComparisonBeforeAfterDTO
  tier1_score: ComparisonBeforeAfterDTO
}

/** One NOT_BUILT entry, display-ready. */
export interface NotBuiltEntryDTO {
  label: string
  detail: string | null
}

/** GET /api/evaluation-report */
export interface EvaluationReportDTO {
  rows: EvalRowDTO[]
  /** Keyed by MPN — only is_known=true rows have an entry (PDSH4816AF, WDTS7024RZ). */
  comparison: Record<string, ComparisonRowDTO>
  not_built: NotBuiltEntryDTO[]
}

// ---------------------------------------------------------------------------
// GET /api/description-formats
// ---------------------------------------------------------------------------

/** Status values as returned by the description-formats endpoint. */
export type DescFieldStatus = 'verbatim' | 'inferred' | 'unverified' | 'contradiction'

/** One source-field entry in the right-panel tag list. */
export interface DescSourceFieldDTO {
  field: string
  status: DescFieldStatus
}

/** The generation-rule block shown in the right panel. */
export interface DescRuleDTO {
  field: string
  confidence: 'high' | 'medium' | 'low'
  is_authoritative: boolean
  char_limit: string
  char_min: number | null
  char_max: number | null
  casing: string
  rule: string
  evidence: string
}

/** One of the 5 format cards. */
export interface DescFormatDTO {
  field: string
  text: string | null
  generated: boolean
  char_count: number
  char_limit: string
  char_min: number | null
  char_max: number | null
  within_limit: boolean
  not_generated_reason: string | null
  source_fields: DescSourceFieldDTO[]
  rule: DescRuleDTO
}

/** GET /api/description-formats */
export interface DescriptionFormatsDTO {
  record: number
  total: number
  mpn: string
  part_desc: string
  is_known: boolean
  category: string
  formats: DescFormatDTO[]
}

// ---------------------------------------------------------------------------
// GET /api/manufacturer-enrichment
// ---------------------------------------------------------------------------

export interface EnrichedFieldDTO {
  field_name: string
  value: string | null
  confidence: 'verbatim' | 'unverified'
  snippet: string | null
}

export interface ManufacturerEnrichmentDTO {
  record: number
  total: number
  mpn: string
  status: 'success' | 'timeout' | 'not_attempted'
  url: string | null
  timestamp: string | null
  page_text_excerpt: string | null
  error: string | null
  fields: EnrichedFieldDTO[]
}
