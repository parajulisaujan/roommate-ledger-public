export type User = {
  email_verified?: boolean;
  verification_required?: boolean;
  id: string;
  name: string;
  email: string;
  diet: string;
  timezone: string;
  currency: string;
  notifications: boolean;
};
export type Household = { id: string; name: string };
export type Member = {
  id: string;
  user_id: string;
  name: string;
  diet: string;
  role: string;
  joined_at: string;
  left_at: string | null;
};
export type Scope = "PERSONAL" | "HOUSEHOLD" | "SELECTED_MEMBERS";
export type ExpenseInput = {
  title: string;
  merchant: string;
  amount: number;
  category: string;
  scope: Scope;
  householdId: string | null;
  payerId: string;
  date: string;
  splitMethod: string;
  participants: string[];
  values: Record<string, number>;
  notes: string;
  version?: number;
};
export type Expense = {
  id: string;
  owner_id: string;
  title: string;
  merchant: string;
  amount: number;
  category: string;
  scope: Scope;
  payer_id: string;
  payer_name: string;
  household_id: string | null;
  expense_date: string;
  notes: string;
  split_method: string;
  receipt_id: string | null;
  version: number;
  allocations?: { user_id: string; amount: number; name: string }[];
};
export type Analytics = {
  total: number;
  personal: number;
  shared: number;
  previousTotal: number;
  difference: number;
  percentChange: number | null;
  month: string;
  categories: { category: string; total: number }[];
  previousCategories: { category: string; total: number }[];
  trend: { month: string; total: number; personal: number; shared: number }[];
};
export type Balance = { id: string; name: string; balance: number };
export type Bill = {
  id: string;
  owner_id: string;
  expense: ExpenseInput;
  next_due: string;
  frequency: string;
  active: boolean;
};
export type ReceiptItem = {
  description: string;
  rawDescription: string;
  quantity: number;
  unitPrice: number | null;
  amount: number;
  category: string;
  confidence: number | null;
  scope: Scope;
  participants: string[];
};
export type Draft = {
  merchant: string;
  date: string;
  currency: string;
  householdId: string | null;
  payerId: string | null;
  items: ReceiptItem[];
  subtotal: number;
  discounts: number;
  tax: number;
  fees: number;
  total: number;
};
export type Receipt = {
  id: string;
  status: string;
  draft: Draft;
  error: string | null;
  duplicate?: boolean;
  created_at: string;
};
export const categories = [
  "Rent",
  "Utilities",
  "Groceries",
  "Dining",
  "Transportation",
  "Insurance",
  "Phone",
  "Subscriptions",
  "Entertainment",
  "Household Supplies",
  "Personal Care",
  "Education",
  "Health",
  "Shopping",
  "Other",
];
