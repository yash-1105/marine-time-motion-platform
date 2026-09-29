/**
 * Browser-visible gateway for the governed Railway API.
 *
 * Keep this relative so browsers only communicate with the Vercel application
 * origin. `next.config.ts` transparently streams the request to Railway without
 * reimplementing or buffering backend behavior in a Next.js route handler.
 */
export const BACKEND_PROXY_BASE = '/api/backend'
