import type {
  DescriptionFormatsDTO,
  DishwasherSchemaDTO,
  EvaluationReportDTO,
} from './api-types'
import { clearStoredSession, getStoredSession, type Session } from './session'

/**
 * Thin client over the FastAPI routes the 4 real screens actually use
 * (backend/main.py has more routes than this — /api/products, /api/ingest,
 * /api/categories, etc. — left over from the pre-pivot fastener-domain UI;
 * this file only wraps what's currently reachable from the app).
 *
 * Paths are relative on purpose — Vite proxies /api to the backend in dev (see
 * vite.config.ts), so no origin is baked into the bundle.
 */

/** A failed request, carrying enough to show the user something specific. */
export class ApiError extends Error {
  // Declared and assigned separately rather than as a constructor parameter
  // property: this project builds with `erasableSyntaxOnly`, which rejects
  // TypeScript syntax that emits runtime code.
  readonly status: number | null

  constructor(message: string, status: number | null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const session = getStoredSession()
  const headers: HeadersInit = { Accept: 'application/json', ...init?.headers }
  if (session) (headers as Record<string, string>).Authorization = `Bearer ${session.token}`

  let response: Response
  try {
    response = await fetch(path, { ...init, headers })
  } catch {
    // fetch only rejects for transport-level failures — the server being down
    // is the overwhelmingly common one in dev, so say that rather than
    // surfacing "Failed to fetch".
    throw new ApiError(
      'Could not reach the API. Is the backend running on port 8000?',
      null,
    )
  }

  if (!response.ok) {
    // A stale/expired token: drop it so the next render falls back to the
    // login screen instead of retrying the same request forever.
    if (response.status === 401) clearStoredSession()

    // FastAPI puts the useful message in `detail`; fall back to the status
    // line when the body is not the shape we expect (a proxy error page, say).
    let detail: string | null = null
    try {
      const body = await response.json()
      detail = typeof body?.detail === 'string' ? body.detail : null
    } catch {
      detail = null
    }
    throw new ApiError(
      detail ?? `Request failed (${response.status})`,
      response.status,
    )
  }

  return (await response.json()) as T
}

/** POST /api/login — exchanges email/password for a signed session token. */
export async function login(email: string, password: string): Promise<Session> {
  return request<Session>('/api/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
}

/** GET /api/dishwasher-schema — the real 15-slot dishwasher attribute scaffold. */
export async function fetchDishwasherSchema(
  signal?: AbortSignal,
): Promise<DishwasherSchemaDTO> {
  return request<DishwasherSchemaDTO>('/api/dishwasher-schema', { signal })
}

/** GET /api/evaluation-report — tier scores, before/after comparison, and NOT_BUILT scope. */
export async function fetchEvaluationReport(
  signal?: AbortSignal,
): Promise<EvaluationReportDTO> {
  return request<EvaluationReportDTO>('/api/evaluation-report', { signal })
}

/** GET /api/description-formats?record=N — per-row description format data. */
export async function fetchDescriptionFormats(
  record: number,
  signal?: AbortSignal,
): Promise<DescriptionFormatsDTO> {
  return request<DescriptionFormatsDTO>(
    `/api/description-formats?record=${record}`,
    { signal },
  )
}

/** GET /api/manufacturer-enrichment?record=N — mock data for manufacturer enrichment. */
export async function fetchManufacturerEnrichment(
  record: number,
  signal?: AbortSignal,
): Promise<import('./api-types').ManufacturerEnrichmentDTO> {
  return request<import('./api-types').ManufacturerEnrichmentDTO>(
    `/api/manufacturer-enrichment?record=${record}`,
    { signal },
  )
}
