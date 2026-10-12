import { PROFILE_FIELDS, type FieldSource, type ProfileValues } from "./schemas";
import type { SessionState } from "./store";

/** Apply validated values; record where each changed field came from. Returns changed fields. */
export function applyProfileUpdate(
  session: SessionState,
  values: Partial<ProfileValues>,
  source: FieldSource,
): string[] {
  const changed: string[] = [];
  const target = session.profile.values as Record<string, unknown>;
  for (const field of PROFILE_FIELDS) {
    if (!(field in values)) continue;
    const next = (values as Record<string, unknown>)[field];
    if (next === undefined || target[field] === next) continue;
    target[field] = next;
    if (next === null) delete session.profile.sources[field];
    else session.profile.sources[field] = source;
    changed.push(field);
  }
  if (changed.length) session.profile.updatedAt = source.at;
  return changed;
}
