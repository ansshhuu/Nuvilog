import type {
  DescriptionFormatsDTO,
  DishwasherSchemaDTO,
  EvaluationReportDTO,
  ManufacturerEnrichmentDTO,
} from '../src/lib/api-types'

/**
 * Canned API payloads for the E2E suite, shaped exactly like the real
 * backend responses (see backend/main.py + frontend/src/lib/api-types.ts).
 * Each spec file installs the routes it needs via page.route() rather than
 * hitting a live FastAPI/Supabase/Gemini backend — that's what keeps the
 * suite hermetic: no quota spend, no shared database state, safe to run in
 * any order or in parallel.
 */

export const VALID_EMAIL = 'admin@example.com'
export const VALID_PASSWORD = 'correct-horse-battery-staple'

export const LOGIN_SUCCESS_RESPONSE = {
  token: 'e2e-fake-session-token',
  email: VALID_EMAIL,
  role: 'ADMIN',
}

export const LOGIN_FAILURE_RESPONSE = {
  detail: 'Invalid email or password',
}

// ---------------------------------------------------------------------------
// GET /api/evaluation-report
// ---------------------------------------------------------------------------

export const KNOWN_MPN = 'WDTS7024RZ'
const OTHER_KNOWN_MPN = 'PDSH4816AF'

export const evaluationReportFixture: EvaluationReportDTO = {
  rows: [
    {
      mpn: OTHER_KNOWN_MPN,
      is_known: true,
      tier1: { score: 240, total: 252 },
      tier2: { score: 11, total: 11 },
      tier3: { score: 176, total: 176, fabrication_violations: 0 },
    },
    {
      mpn: KNOWN_MPN,
      is_known: true,
      tier1: { score: 252, total: 252 },
      tier2: { score: 11, total: 11 },
      tier3: { score: 176, total: 176, fabrication_violations: 0 },
    },
    {
      mpn: 'THIN-ROW-001',
      is_known: false,
      tier1: null,
      tier2: { score: 11, total: 11 },
      tier3: { score: 177, total: 177, fabrication_violations: 0 },
    },
  ],
  comparison: {
    [OTHER_KNOWN_MPN]: {
      descriptions_nonempty: { baseline: '2/5', enriched: '2/5' },
      attributes_verified: { baseline: '0/15', enriched: '0/15' },
      tier1_score: { baseline: '235/252', enriched: '240/252' },
    },
    [KNOWN_MPN]: {
      descriptions_nonempty: { baseline: '2/5', enriched: '5/5' },
      attributes_verified: { baseline: '0/15', enriched: '4/15' },
      tier1_score: { baseline: '248/252', enriched: '252/252' },
    },
  },
  not_built: [
    { label: 'WASHER', detail: '8 rows, no ground truth' },
    { label: 'SEARCH-BASED ENRICHMENT', detail: 'requires paid API' },
  ],
}

// ---------------------------------------------------------------------------
// GET /api/description-formats
// ---------------------------------------------------------------------------

export function descriptionFormatsFixture(record: number): DescriptionFormatsDTO {
  return {
    record,
    total: 2,
    mpn: KNOWN_MPN,
    part_desc: 'DISHWASHER BUILT IN EnergyStar ECO 24IN',
    is_known: true,
    category: 'DISHWASHER',
    formats: [
      {
        field: 'INVOICE_DESC',
        text: 'WDTS7024RZ DISHWASHER BUILT IN',
        generated: true,
        char_count: 31,
        char_limit: '40',
        char_min: null,
        char_max: 40,
        within_limit: true,
        not_generated_reason: null,
        source_fields: [
          { field: 'Mfg_Part_Num', status: 'verbatim' },
          { field: 'Part_Desc', status: 'verbatim' },
        ],
        rule: {
          field: 'INVOICE_DESC',
          confidence: 'high',
          is_authoritative: true,
          char_limit: '40',
          char_min: null,
          char_max: 40,
          casing: 'ALL CAPS',
          rule: 'Mfg_Part_Num + Part_Desc, space-joined, truncated to 40 chars.',
          evidence: 'Matches every INVOICE_DESC in the delivery CSV byte-for-byte.',
        },
      },
      {
        field: 'MOBILE_DESC',
        text: 'Whirlpool WDTS7024RZ dishwasher, built-in, EnergyStar',
        generated: true,
        char_count: 54,
        char_limit: '60-80',
        char_min: 60,
        char_max: 80,
        within_limit: false,
        not_generated_reason: null,
        source_fields: [
          { field: 'BRAND_NAME', status: 'verbatim' },
          { field: 'MANUFACTURER_NAME', status: 'inferred' },
          { field: 'Mfg_Part_Num', status: 'verbatim' },
          { field: 'Part_Desc', status: 'verbatim' },
        ],
        rule: {
          field: 'MOBILE_DESC',
          confidence: 'medium',
          is_authoritative: false,
          char_limit: '60-80',
          char_min: 60,
          char_max: 80,
          casing: 'Title Case / Mixed',
          rule: 'BRAND_NAME + model line + Mfg_Part_Num + Part_Desc, comma-joined.',
          evidence: 'Inferred from 2 known rows only — below the confidence bar for authoritative.',
        },
      },
      {
        field: 'SHORT_DESC',
        text: null,
        generated: false,
        char_count: 0,
        char_limit: '80',
        char_min: null,
        char_max: 80,
        within_limit: true,
        not_generated_reason: 'rule confidence too low: only 2 known rows to derive a pattern from',
        source_fields: [
          { field: 'BRAND_NAME', status: 'verbatim' },
          { field: 'Mfg_Part_Num', status: 'verbatim' },
          { field: 'Part_Desc', status: 'verbatim' },
        ],
        rule: {
          field: 'SHORT_DESC',
          confidence: 'low',
          is_authoritative: false,
          char_limit: '80',
          char_min: null,
          char_max: 80,
          casing: 'Title Case / Mixed',
          rule: 'Not enough examples to derive a construction rule.',
          evidence: 'Only 2 known rows to derive a pattern from.',
        },
      },
      {
        field: 'LONG_DESC1',
        text: null,
        generated: false,
        char_count: 0,
        char_limit: '60-80',
        char_min: 60,
        char_max: 80,
        within_limit: true,
        not_generated_reason: 'rule confidence too low: only 2 known rows to derive a pattern from',
        source_fields: [
          { field: 'BRAND_NAME', status: 'verbatim' },
          { field: 'Part_Desc', status: 'verbatim' },
          { field: 'ATTRIBUTE_VALUE 1', status: 'inferred' },
          { field: 'ATTRIBUTE_VALUE 3', status: 'inferred' },
          { field: 'ATTRIBUTE_VALUE 15', status: 'inferred' },
        ],
        rule: {
          field: 'LONG_DESC1',
          confidence: 'low',
          is_authoritative: false,
          char_limit: '60-80',
          char_min: 60,
          char_max: 80,
          casing: 'Title Case / Mixed',
          rule: 'Not enough examples to derive a construction rule.',
          evidence: 'Only 2 known rows to derive a pattern from.',
        },
      },
      {
        field: 'MARKETING_DESCRIPTION',
        text: null,
        generated: false,
        char_count: 0,
        char_limit: '100-150',
        char_min: 100,
        char_max: 150,
        within_limit: true,
        not_generated_reason: 'rule confidence too low: no verified marketing copy pattern found',
        source_fields: [
          { field: 'BRAND_NAME', status: 'verbatim' },
          { field: 'Part_Desc', status: 'inferred' },
          { field: 'ATTRIBUTE_VALUE 1', status: 'unverified' },
        ],
        rule: {
          field: 'MARKETING_DESCRIPTION',
          confidence: 'low',
          is_authoritative: false,
          char_limit: '100-150',
          char_min: 100,
          char_max: 150,
          casing: 'Title Case / Mixed',
          rule: 'Not enough examples to derive a construction rule.',
          evidence: 'No verified marketing copy pattern found.',
        },
      },
    ],
  }
}

/** Shape of the 400 the real backend sends for an out-of-range `record`. */
export function descriptionFormatsOutOfRangeError(record: number, total: number) {
  return { detail: `record must be 0–${total - 1}; got ${record}.` }
}

// ---------------------------------------------------------------------------
// GET /api/manufacturer-enrichment
// ---------------------------------------------------------------------------

/** The real 15-label dishwasher scaffold order (see dishwasher_schema.py). */
const DISHWASHER_LABELS = [
  'Series',
  'Size',
  'Sound Level',
  'Additional Information',
  'Capacity',
  'Control Type',
  'Color/Finish',
  'Installation Type',
  'Energy Star Certified',
  'Number of Wash Cycles',
  'Number of Racks',
  'Third Rack',
  'Wash Cycle Options',
  'Warranty',
  'Voltage',
]

export function manufacturerEnrichmentSuccessFixture(
  record: number,
): ManufacturerEnrichmentDTO {
  const verified = new Set(['Series', 'Size', 'Sound Level', 'Additional Information'])
  return {
    record,
    total: 3,
    mpn: KNOWN_MPN,
    status: 'success',
    url: 'https://learnwhirlpool.com/product/wdts7024rz',
    timestamp: '2026-08-20T14:32:07Z',
    page_text_excerpt:
      'Load more and run less with our quietest and largest capacity dishwasher. ' +
      'The Eco Series WDTS7024RZ brings advanced cleaning... 24 in W x 24-1/4 in D size. ' +
      'Sound level is 41 dBA...',
    error: null,
    fields: DISHWASHER_LABELS.map((label) => {
      if (!verified.has(label)) {
        return { field_name: label, value: null, confidence: 'unverified' as const, snippet: null }
      }
      const value: Record<string, string> = {
        Series: 'Eco Series',
        Size: '24 in W x 24-1/4 in D',
        'Sound Level': '41',
        'Additional Information':
          'Load more and run less with our quietest and largest capacity dishwasher.',
      }
      const snippet: Record<string, string> = {
        Series: 'The Eco Series WDTS7024RZ brings advanced cleaning...',
        Size: '24 in W x 24-1/4 in D size.',
        'Sound Level': 'Sound level is 41 dBA...',
        'Additional Information':
          'Load more and run less with our quietest and largest capacity dishwasher.',
      }
      return {
        field_name: label,
        value: value[label],
        confidence: 'verbatim' as const,
        snippet: snippet[label],
      }
    }),
  }
}

/** The timeout case: fetch_manufacturer_page returned None. Every field must
 * come back honestly unresolved — this is the documented, expected failure
 * mode (see backend/pipeline/manufacturer_enrichment.py's module docstring),
 * not a crash. */
export function manufacturerEnrichmentTimeoutFixture(
  record: number,
): ManufacturerEnrichmentDTO {
  return {
    record,
    total: 3,
    mpn: 'PDSH4816AF',
    status: 'timeout',
    url: 'https://www.frigidaire.com/en/p/kitchen/dishwashers/built-in-dishwashers/PDSH4816AF',
    timestamp: '2026-08-20T14:35:41Z',
    page_text_excerpt: null,
    error: 'Source unreachable — request timed out after 10s',
    fields: DISHWASHER_LABELS.map((label) => ({
      field_name: label,
      value: null,
      confidence: 'unverified' as const,
      snippet: null,
    })),
  }
}

export function manufacturerEnrichmentNotAttemptedFixture(
  record: number,
): ManufacturerEnrichmentDTO {
  return {
    record,
    total: 3,
    mpn: 'THIN-ROW-001',
    status: 'not_attempted',
    url: null,
    timestamp: null,
    page_text_excerpt: null,
    error: null,
    fields: DISHWASHER_LABELS.map((label) => ({
      field_name: label,
      value: null,
      confidence: 'unverified' as const,
      snippet: null,
    })),
  }
}

// ---------------------------------------------------------------------------
// GET /api/dishwasher-schema
// ---------------------------------------------------------------------------

export const dishwasherSchemaFixture: DishwasherSchemaDTO = {
  category: 'DISHWASHER',
  display_name: 'Dishwasher',
  description: 'The only sub-type with ground-truth evidence behind its attribute scaffold.',
  fields: DISHWASHER_LABELS.map((label, index) => ({
    index,
    label,
    unit: label === 'Sound Level' ? 'dBA' : null,
    evidence: 'Confirmed against both known ground-truth rows.',
  })),
}
