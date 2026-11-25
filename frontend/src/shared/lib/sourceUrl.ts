export function sourceUrl(value?: string | null): string | undefined {
  if (!value || !URL.canParse(value)) return
  const url = new URL(value)
  if (url.protocol === 'https:' || url.protocol === 'http:') return url.href
}
