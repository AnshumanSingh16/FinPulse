/** Link to the Evidence view focused on one evidence item (and optionally an investigation). */
export function evidenceHref(
  entityId: string,
  item: string,
  opts: { asOf?: string | null; investigation?: string | null; claim?: string | null } = {},
): string {
  const q = new URLSearchParams();
  if (opts.asOf) q.set("asOf", opts.asOf);
  if (opts.investigation) q.set("investigation", opts.investigation);
  if (opts.claim) q.set("claim", opts.claim);
  q.set("item", item);
  return `/entities/${entityId}/evidence?${q.toString()}`;
}
