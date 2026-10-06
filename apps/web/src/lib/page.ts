/** Route props shared by the entity pages (Next.js passes params as promises). */
export type EntityPageProps = {
  params: Promise<{ entityId: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

export function one(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

/** The entity and the as-of date ("asOf=YYYY-MM-DD"; absent = end of the data). */
export async function entityContext(props: EntityPageProps) {
  const { entityId } = await props.params;
  const search = await props.searchParams;
  const raw = one(search.asOf);
  const asOf = raw && /^\d{4}-\d{2}-\d{2}$/.test(raw) ? raw : undefined;
  return { entityId, asOf, search };
}
