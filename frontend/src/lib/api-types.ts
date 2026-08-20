/**
 * Wire shapes, mirrored 1:1 from the backend so responses can be consumed
 * without reshaping.
 */

/**
 * backend/pipeline/dishwasher_schema.py::DishwasherAttribute, as returned in
 * DishwasherSchemaDTO.fields. Deliberately narrower than a general schema
 * field type — the dataclass it mirrors has no `type`, `required`, or
 * `valid_range` concept, so this type doesn't carry fields that don't exist
 * server-side.
 */
export interface DishwasherFieldDTO {
  index: number
  label: string
  unit: string | null
  evidence: string
}

/** GET /api/dishwasher-schema */
export interface DishwasherSchemaDTO {
  category: string
  display_name: string
  description: string
  fields: DishwasherFieldDTO[]
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
