export function cents(value: string): number {
  if (!/^\d+(\.\d{0,2})?$/.test(value.trim()))
    throw new Error("Use a positive amount with at most two decimal places.");
  const [whole, decimal = ""] = value.trim().split(".");
  const result = BigInt(whole) * 100n + BigInt(decimal.padEnd(2, "0"));
  if (result > 100000000000n) throw new Error("Amount is too large.");
  return Number(result);
}
export function dollars(value: number): string {
  return `${Math.floor(value / 100)}.${String(value % 100).padStart(2, "0")}`;
}
export function money(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  }).format(value / 100);
}
export function today(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}
export function equalPreview(total: number, count: number): string {
  if (!count) return "Choose participants";
  return total % count
    ? `${money(Math.floor(total / count))}–${money(Math.ceil(total / count))} each`
    : `${money(total / count)} each`;
}
