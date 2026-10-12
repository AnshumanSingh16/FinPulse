/** Raised when a financial tool receives an input it cannot calculate with. */
export class FinanceInputError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "FinanceInputError";
  }
}

export function requireFinite(name: string, value: number): void {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new FinanceInputError(`${name} must be a finite number`);
  }
}

export function requireNonNegative(name: string, value: number): void {
  requireFinite(name, value);
  if (value < 0) throw new FinanceInputError(`${name} cannot be negative`);
}

/** Round to the nearest paisa (2 decimals) without binary-float surprises like 1.005. */
export function roundPaise(value: number): number {
  return Math.round((value + Number.EPSILON) * 100) / 100;
}

/** Round to whole rupees: how figures are shown to the user. */
export function roundRupees(value: number): number {
  return Math.round(value);
}
