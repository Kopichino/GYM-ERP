import { api } from "../lib/api";

export interface ExpenseCategory {
  id: number;
  name: string;
  description: string;
  is_active: boolean;
  expense_count: number;
}

export interface Expense {
  id: number;
  category: number;
  category_name: string;
  amount: string;
  spent_on: string;
  vendor: string;
  reference: string;
  notes: string;
  receipt: string | null;
  recorded_by: number | null;
  recorded_by_name: string | null;
  created_at: string;
}

export interface ExpenseSummary {
  total: string;
  count: number;
  by_category: { category: string; total: string }[];
}

export async function fetchExpenseCategories() {
  return (await api.get<{ results: ExpenseCategory[] }>("/expenses/categories/")).data.results;
}

export async function createExpenseCategory(payload: { name: string; description?: string }) {
  return (await api.post<ExpenseCategory>("/expenses/categories/", payload)).data;
}

export async function fetchExpenses(filters: { from?: string; to?: string; category?: number } = {}) {
  return (await api.get<{ results: Expense[] }>("/expenses/", { params: filters })).data.results;
}

export async function fetchExpenseSummary(filters: { from?: string; to?: string } = {}) {
  return (await api.get<ExpenseSummary>("/expenses/summary/", { params: filters })).data;
}

export async function createExpense(payload: {
  category: number;
  amount: string;
  spent_on: string;
  vendor?: string;
  reference?: string;
  notes?: string;
}) {
  return (await api.post<Expense>("/expenses/", payload)).data;
}

export async function deleteExpense(id: number) {
  await api.delete(`/expenses/${id}/`);
}
