export function contentLooksLikeHtml(value: string) {
  return /<\/?[a-z][\s\S]*>/i.test(value || "");
}
