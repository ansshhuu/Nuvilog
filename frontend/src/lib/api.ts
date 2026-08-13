import type {
  ProductDTO,
  ProductListDTO,
  ProductSummaryDTO,
  StatusChangeDTO,
} from './api-types'

/**
 * Thin client over the FastAPI routes in backend/main.py.
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
  let response: Response
  try {
    response = await fetch(path, {
      ...init,
      headers: { Accept: 'application/json', ...init?.headers },
    })
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

/** GET /api/products — every product with its fields and flags, newest first. */
export async function fetchProducts(
  signal?: AbortSignal,
): Promise<ProductSummaryDTO[]> {
  const data = await request<ProductListDTO>('/api/products', { signal })
  return data.products
}

/** GET /api/products/{id} — one product, including ranked review findings. */
export async function fetchProduct(
  id: string,
  signal?: AbortSignal,
): Promise<ProductDTO> {
  return request<ProductDTO>(`/api/products/${encodeURIComponent(id)}`, {
    signal,
  })
}

/** POST /api/products/{id}/approve — sets status to "approved". */
export async function approveProduct(id: string): Promise<StatusChangeDTO> {
  return request<StatusChangeDTO>(
    `/api/products/${encodeURIComponent(id)}/approve`,
    { method: 'POST' },
  )
}

/** POST /api/products/{id}/mark-for-review — sets status to "needs_review". */
export async function markProductForReview(
  id: string,
): Promise<StatusChangeDTO> {
  return request<StatusChangeDTO>(
    `/api/products/${encodeURIComponent(id)}/mark-for-review`,
    { method: 'POST' },
  )
}
