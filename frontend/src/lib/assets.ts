export function withBaseUrl(path: string): string {
  if (!path) return path;
  if (/^(?:[a-z]+:)?\/\//i.test(path)) return path;

  const baseUrl = import.meta.env.BASE_URL.endsWith("/")
    ? import.meta.env.BASE_URL
    : `${import.meta.env.BASE_URL}/`;

  return `${baseUrl}${path.replace(/^\/+/, "")}`;
}

export function withApiBaseUrl(path?: string): string {
  if (!path) return "";
  if (/^(?:[a-z]+:)?\/\//i.test(path) || path.startsWith("data:") || path.startsWith("blob:")) {
    return path;
  }

  const baseUrl = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/+$/, "");
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${baseUrl}${normalizedPath}`;
}
