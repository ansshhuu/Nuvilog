import type { SourceTable } from '@/components/SourceSnippetPanel'
import type { ProductDTO, ProductFieldDTO } from '@/lib/api-types'

/**
 * Placeholder detail for HXMB825250, in the exact shape of
 * GET /api/products/{id}. Replaced by a fetch later — nothing downstream
 * reshapes this, so only the source swaps.
 */
export const MOCK_PRODUCT_DETAIL: ProductDTO = {
  id: 'HXMB825250',
  category: 'fasteners',
  description: null,
  raw_input_type: 'pdf',
  raw_input_ref: 'fastener_import_may/hxmb825250.pdf',
  status: 'reviewed',
  created_at: '2026-05-04T09:12:00Z',
  fields: [
    {
      field_name: 'product_name',
      value: 'Hex Bolt M8 x 25mm',
      confidence_level: 'high',
      evidence_type: 'exact_match',
      source_snippet: 'Product Name | Hex Bolt M8 x 25mm',
      inference_chain: null,
      is_ai_generated: false,
    },
    {
      field_name: 'material',
      value: 'Stainless Steel A2',
      confidence_level: 'high',
      evidence_type: 'exact_match',
      source_snippet: 'Material | Stainless Steel A2',
      inference_chain: null,
      is_ai_generated: false,
    },
    {
      field_name: 'diameter',
      value: 'M8',
      confidence_level: 'high',
      evidence_type: 'exact_match',
      source_snippet: 'Diameter | M8',
      inference_chain: null,
      is_ai_generated: false,
    },
    {
      field_name: 'length',
      value: '25 mm',
      confidence_level: 'high',
      evidence_type: 'exact_match',
      source_snippet: 'Length | 25 mm',
      inference_chain: null,
      is_ai_generated: false,
    },
    {
      field_name: 'thread_pitch',
      value: '1.25 mm',
      confidence_level: 'medium',
      evidence_type: 'contextual_inference',
      source_snippet: 'All threads conform to ISO 261 metric coarse series.',
      inference_chain: 'Inferred from standard metric coarse thread',
      is_ai_generated: false,
    },
    {
      field_name: 'finish',
      value: 'Zinc Plated',
      confidence_level: 'unverified',
      evidence_type: 'none',
      source_snippet: null,
      inference_chain: null,
      is_ai_generated: true,
    },
    {
      field_name: 'strength_class',
      value: 'A2-70',
      confidence_level: 'high',
      evidence_type: 'exact_match',
      source_snippet: 'Strength class A2-70 per EN ISO 3506.',
      inference_chain: null,
      is_ai_generated: false,
    },
    {
      field_name: 'head_type',
      value: 'Hexagonal',
      confidence_level: 'high',
      evidence_type: 'exact_match',
      source_snippet: 'Head Type | Hexagonal',
      inference_chain: null,
      is_ai_generated: false,
    },
  ],
  flags: [
    {
      field_name: 'strength_class',
      issue_type: 'contradiction',
      message: 'Conflicting values found',
    },
  ],
  review_findings: [
    {
      field_name: 'strength_class',
      issue_type: 'contradiction',
      message: 'Conflicting values found',
    },
    {
      field_name: 'finish',
      issue_type: 'unverified',
      message: 'No clear mention found',
    },
  ],
}

/**
 * Page/table locations shown in the SOURCE column.
 *
 * These are mock-only. The backend persists `source_snippet` (the matched
 * text) but no page or table coordinates — input_handler.py concatenates page
 * text without recording which page each span came from, so "Page 1 - Table 1"
 * is not currently derivable from a real response. Wired through
 * `sourceLabelFor` so the table renders live data the moment the backend can
 * supply it, and degrades to "No source" until then.
 */
export const MOCK_SOURCE_LABELS: Record<string, string> = {
  product_name: 'Page 1 - Table 1',
  material: 'Page 1 - Table 1',
  diameter: 'Page 1 - Table 1',
  length: 'Page 1 - Table 1',
  thread_pitch: 'Page 2 - Text Block',
  finish: 'Page 2 - Note 2',
  strength_class: 'Page 1 - Note 2, Page 3 - Table 2',
  head_type: 'Page 1 - Table 1',
}

export function mockSourceLabelFor(field: ProductFieldDTO): string | null {
  return MOCK_SOURCE_LABELS[field.field_name] ?? null
}

/**
 * The source document's own table, as rendered in the right-hand panel.
 *
 * Also mock-only, and a wider gap than the page labels: stage 1 does parse
 * tables (RawDocument.tables), but nothing persists them — the products and
 * product_fields tables have no column for a table, so a real response cannot
 * reconstruct this grid. Only fields whose evidence is a table row have one
 * here; a field sourced from a text block or a note correctly resolves to
 * null and the panel falls back.
 */
const SPEC_TABLE: SourceTable = {
  label: 'Page 1 - Table 1',
  rows: [
    { item: 'Product Name', specification: 'Hex Bolt M8 x 25mm', fieldName: 'product_name' },
    { item: 'Material', specification: 'Stainless Steel A2', fieldName: 'material' },
    { item: 'Diameter', specification: 'M8', fieldName: 'diameter' },
    { item: 'Length', specification: '25 mm', fieldName: 'length' },
    { item: 'Thread Pitch', specification: '-', fieldName: 'thread_pitch' },
    { item: 'Finish', specification: '-', fieldName: 'finish' },
    { item: 'Head Type', specification: 'Hexagonal', fieldName: 'head_type' },
  ],
}

const FIELDS_WITH_TABLE_EVIDENCE = new Set([
  'product_name',
  'material',
  'diameter',
  'length',
  'head_type',
])

export function mockSourceTableFor(fieldName: string): SourceTable | null {
  return FIELDS_WITH_TABLE_EVIDENCE.has(fieldName) ? SPEC_TABLE : null
}
