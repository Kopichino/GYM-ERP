import { api } from "../lib/api";

/** Every level of a plan reports the same four numbers, all derived server-side. */
export interface Macros {
  calories: string;
  protein_g: string;
  carbs_g: string;
  fat_g: string;
}

export interface FoodItem {
  id: number;
  name: string;
  category: string;
  category_name: string;
  /** All values are per 100 g -- portions are a single multiplication. */
  calories: string;
  protein_g: string;
  carbs_g: string;
  fat_g: string;
  serving_label: string;
  serving_grams: string | null;
  is_active: boolean;
}

export interface DietMealItem {
  id: number;
  meal: number;
  food: number;
  food_name: string;
  serving_label: string;
  serving_grams: string | null;
  quantity_g: string;
  order: number;
  macros: Macros;
}

export const MEAL_TYPES = [
  { value: "breakfast", label: "Breakfast" },
  { value: "snack_am", label: "Mid-morning snack" },
  { value: "lunch", label: "Lunch" },
  { value: "pre_workout", label: "Pre-workout" },
  { value: "post_workout", label: "Post-workout" },
  { value: "snack_pm", label: "Evening snack" },
  { value: "dinner", label: "Dinner" },
] as const;

export interface DietMeal {
  id: number;
  day: number;
  meal_type: string;
  meal_type_name: string;
  order: number;
  notes: string;
  items: DietMealItem[];
  macros: Macros;
}

export interface DietDay {
  id: number;
  plan: number;
  /** 0 = Monday, matching Python's date.weekday(). */
  weekday: number;
  weekday_name: string;
  label: string;
  display_label: string;
  notes: string;
  meals: DietMeal[];
  macros: Macros;
}

export type DietGoal = "cut" | "maintain" | "bulk";

export const DIET_GOALS: { value: DietGoal; label: string }[] = [
  { value: "cut", label: "Fat loss" },
  { value: "maintain", label: "Maintenance" },
  { value: "bulk", label: "Muscle gain" },
];

export interface DietPlan {
  id: number;
  user: number;
  name: string;
  goal: DietGoal;
  goal_name: string;
  target_calories: number | null;
  target_protein_g: number | null;
  notes: string;
  created_by: number | null;
  created_by_name: string | null;
  is_active: boolean;
  days_planned: number;
  /** The plan's daily average, so it compares honestly with target_calories. */
  daily_macros: Macros;
  days: DietDay[];
  created_at: string;
}

export interface TodayDiet {
  has_plan: boolean;
  weekday_name: string;
  is_planned_day: boolean;
  day: DietDay | null;
}

/** `member` lets a trainer or admin work on one of their people's plans. */
const scope = (member?: number) => (member ? { params: { member } } : undefined);

/** The catalogue comes back unpaginated -- the picker offers all of it. */
export async function fetchFoods(search?: string) {
  const res = await api.get<{ results: FoodItem[] } | FoodItem[]>("/nutrition/foods/", {
    params: { search: search || undefined },
  });
  return Array.isArray(res.data) ? res.data : res.data.results;
}

export async function fetchDietPlans(member?: number) {
  const res = await api.get<{ results: DietPlan[] }>("/nutrition/plans/", scope(member));
  return res.data.results;
}

export async function fetchTodayDiet() {
  const res = await api.get<TodayDiet>("/nutrition/plans/today/");
  return res.data;
}

export async function createDietPlan(
  payload: { name: string; goal?: DietGoal; target_calories?: number | null },
  member?: number
) {
  const res = await api.post<DietPlan>("/nutrition/plans/", payload, scope(member));
  return res.data;
}

export async function updateDietPlan(id: number, payload: Partial<DietPlan>, member?: number) {
  const res = await api.patch<DietPlan>(`/nutrition/plans/${id}/`, payload, scope(member));
  return res.data;
}

export async function activateDietPlan(id: number, member?: number) {
  const res = await api.post<DietPlan>(`/nutrition/plans/${id}/activate/`, {}, scope(member));
  return res.data;
}

export async function deleteDietPlan(id: number, member?: number) {
  await api.delete(`/nutrition/plans/${id}/`, scope(member));
}

export async function addDietDay(
  payload: { plan: number; weekday: number; label?: string },
  member?: number
) {
  const res = await api.post<DietDay>("/nutrition/days/", payload, scope(member));
  return res.data;
}

export async function deleteDietDay(id: number, member?: number) {
  await api.delete(`/nutrition/days/${id}/`, scope(member));
}

export async function addDietMeal(
  payload: { day: number; meal_type: string },
  member?: number
) {
  const res = await api.post<DietMeal>("/nutrition/meals/", payload, scope(member));
  return res.data;
}

export async function deleteDietMeal(id: number, member?: number) {
  await api.delete(`/nutrition/meals/${id}/`, scope(member));
}

export async function addDietItem(
  payload: { meal: number; food: number; quantity_g: string },
  member?: number
) {
  const res = await api.post<DietMealItem>("/nutrition/items/", payload, scope(member));
  return res.data;
}

export async function deleteDietItem(id: number, member?: number) {
  await api.delete(`/nutrition/items/${id}/`, scope(member));
}

/** Adjusting a portion in place, rather than deleting and re-adding it. */
export async function updateDietItem(
  id: number,
  payload: { quantity_g: string },
  member?: number
) {
  const res = await api.patch<DietMealItem>(`/nutrition/items/${id}/`, payload, scope(member));
  return res.data;
}

export async function updateDietDay(
  id: number,
  payload: { label?: string; notes?: string },
  member?: number
) {
  const res = await api.patch<DietDay>(`/nutrition/days/${id}/`, payload, scope(member));
  return res.data;
}
