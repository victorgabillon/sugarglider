// Exact binary-float formatting compatible with Python's fixed decimal output.
// Used by canonical signatures and GPX; never rounds stored route geometry.
export function canonicalFixed(value, digits) {
  if (!Number.isFinite(value) || !Number.isSafeInteger(digits) || digits < 0 || digits > 12) {
    throw new TypeError("Invalid canonical number formatting input.");
  }
  const data = new DataView(new ArrayBuffer(8));
  data.setFloat64(0, value);
  const bits = data.getBigUint64(0);
  const negative = (bits >> 63n) !== 0n;
  const exponent = Number((bits >> 52n) & 0x7ffn);
  let numerator = bits & ((1n << 52n) - 1n);
  if (exponent) numerator += 1n << 52n;
  const power = (exponent || 1) - 1023 - 52;
  numerator *= 10n ** BigInt(digits);
  const denominator = power < 0 ? 1n << BigInt(-power) : 1n;
  if (power > 0) numerator <<= BigInt(power);
  let rounded = numerator / denominator;
  const remainder = numerator % denominator;
  if (2n * remainder > denominator || (2n * remainder === denominator && rounded % 2n !== 0n)) rounded += 1n;
  const text = rounded.toString().padStart(digits + 1, "0");
  return `${negative ? "-" : ""}${digits ? `${text.slice(0, -digits)}.${text.slice(-digits)}` : text}`;
}
