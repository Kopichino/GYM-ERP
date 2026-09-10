import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { useMemo, useState } from "react";
import {
  addDietDay,
  addDietItem,
  addDietMeal,
  createDietPlan,
  deleteDietDay,
  deleteDietItem,
  deleteDietMeal,
  fetchDietPlans,
  fetchFoods,
  updateDietItem,
  DIET_GOALS,
  MEAL_TYPES,
  type DietDay,
  type DietGoal,
  type DietMeal,
  type DietMealItem,
  type DietPlan,
  type FoodItem,
  type Macros,
} from "../api/nutrition";
import { WEEKDAYS } from "../api/workouts";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  ErrorText,
  Input,
  LoadingState,
  Select, ghostButtonClass } from "./ui";
import { railColor } from "../lib/theme";

const todayWeekday = () => (new Date().getDay() + 6) % 7; // JS Sunday=0 -> Monday=0

const round = (value: string | number) => Math.round(Number(value));

/** How much one tap of + or - moves a portion: a whole serving where the food
 *  has one ("1 roti", "1 scoop"), otherwise a round 10g. Nudging chicken by
 *  1g is nobody's idea of planning a meal. */
function stepFor(servingGrams: string | null) {
  const serving = Number(servingGrams ?? 0);
  return serving > 0 ? serving : 10;
}

/** "2 rotis" reads better than "80g" -- but only when the food has a serving
 *  size and the quantity is a sensible multiple of it. */
function servingText(grams: number, label: string, servingGrams: string | null) {
  const serving = Number(servingGrams ?? 0);
  if (!label || serving <= 0) return "";
  const count = grams / serving;
  const rounded = Math.round(count * 2) / 2; // halves are still readable
  if (Math.abs(count - rounded) > 0.05 || rounded <= 0) return "";
  const shown = rounded % 1 === 0 ? String(rounded) : rounded.toFixed(1);
  // Labels are written as "1 cup", "1 roti", "10 almonds". Where the label is
  // already "one of something", swap in the real count -- "2 cup" beats the
  // "2 x 1 cup" that a naive multiplier produces.
  return label.startsWith("1 ") ? `${shown} ${label.slice(2)}` : `${shown} x ${label}`;
}

/** The four numbers, laid out in a fixed order so the eye can compare rows. */
function MacroRow({ macros, className = "" }: { macros: Macros; className?: string }) {
  return (
    <span className={`tabular-nums text-xs text-[var(--color-text-muted)] ${className}`}>
      <b className="text-[var(--color-text)]">{round(macros.calories)}</b> kcal
      <span className="mx-1.5 opacity-40">|</span>P {round(macros.protein_g)}
      <span className="mx-1.5 opacity-40">|</span>C {round(macros.carbs_g)}
      <span className="mx-1.5 opacity-40">|</span>F {round(macros.fat_g)}
    </span>
  );
}

/** How far today's plan is towards the calorie target. */
function TargetBar({ kcal, target }: { kcal: number; target: number | null }) {
  if (!target) return null;
  const pct = Math.min((kcal / target) * 100, 100);
  const over = kcal > target;
  const gap = Math.abs(kcal - target);
  return (
    <div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-[var(--color-surface-2)]">
        <div
          className="h-full rounded-full transition-[width] duration-300"
          style={{ width: `${pct}%`, background: over ? "#ffb020" : "var(--color-accent)" }}
        />
      </div>
      <p className="mt-1 text-xs text-[var(--color-text-muted)]">
        {gap === 0
          ? `Exactly on the ${target} kcal target`
          : `${gap} kcal ${over ? "over" : "under"} the ${target} target`}
      </p>
    </div>
  );
}

/**
 * One portion. The grams are editable in place -- previously the only way to
 * change 200g of rice to 150g was to delete it and add it again, which is what
 * made the screen feel like arithmetic homework.
 */
function PortionRow({
  item,
  member,
  target,
}: {
  item: DietMealItem;
  member?: number;
  target: number | null;
}) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState(String(round(item.quantity_g)));
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["diet"] });

  const save = useMutation({
    mutationFn: (grams: number) => updateDietItem(item.id, { quantity_g: String(grams) }, member),
    onSuccess: refresh,
  });
  const remove = useMutation({
    mutationFn: () => deleteDietItem(item.id, member),
    onSuccess: refresh,
  });

  const grams = round(item.quantity_g);
  const step = stepFor(item.serving_grams);

  function commit(next: number) {
    const clamped = Math.max(1, Math.round(next));
    setDraft(String(clamped));
    if (clamped !== grams) save.mutate(clamped);
  }

  const serving = servingText(grams, item.serving_label, item.serving_grams);
  // The share of the day's target this one portion accounts for, which is what
  // makes "is this too much rice?" answerable at a glance.
  const share = target ? Math.round((Number(item.macros.calories) / target) * 100) : null;

  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-[var(--color-border)] py-2 last:border-none">
      <span className="min-w-0 flex-1 text-sm text-[var(--color-text)]">
        {item.food_name}
        {serving && (
          <span className="ml-2 text-xs text-[var(--color-text-muted)]">{serving}</span>
        )}
      </span>

      <span className="flex shrink-0 items-center gap-1">
        <button
          onClick={() => commit(grams - step)}
          disabled={save.isPending || grams - step < 1}
          aria-label={`Less ${item.food_name}`}
          className="h-7 w-7 rounded-md border border-[var(--color-border)] text-[var(--color-text-muted)] transition-colors hover:border-[var(--color-accent)] hover:text-[var(--color-text)] disabled:opacity-30"
        >
          -
        </button>
        <span className="relative">
          <Input
            type="number"
            min={1}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={() => commit(Number(draft) || grams)}
            onKeyDown={(e) => {
              if (e.key === "Enter") e.currentTarget.blur();
            }}
            className="w-[84px] px-2 py-1 pr-6 text-center text-sm"
          />
          <span className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-xs text-[var(--color-text-muted)]">
            g
          </span>
        </span>
        <button
          onClick={() => commit(grams + step)}
          disabled={save.isPending}
          aria-label={`More ${item.food_name}`}
          className="h-7 w-7 rounded-md border border-[var(--color-border)] text-[var(--color-text-muted)] transition-colors hover:border-[var(--color-accent)] hover:text-[var(--color-text)] disabled:opacity-30"
        >
          +
        </button>
      </span>

      <span className="w-[110px] shrink-0 text-right tabular-nums text-sm text-[var(--color-text)]">
        {round(item.macros.calories)}
        <span className="text-xs text-[var(--color-text-muted)]"> kcal</span>
        {share !== null && (
          <span className="ml-1 text-[10px] text-[var(--color-text-muted)]">({share}%)</span>
        )}
      </span>
      <span className="w-[130px] shrink-0 text-right tabular-nums text-xs text-[var(--color-text-muted)]">
        P {round(item.macros.protein_g)} · C {round(item.macros.carbs_g)} · F{" "}
        {round(item.macros.fat_g)}
      </span>

      <button
        onClick={() => remove.mutate()}
        aria-label={`Remove ${item.food_name}`}
        className={`${ghostButtonClass} shrink-0`}
      >
        &times;
      </button>
    </li>
  );
}

/**
 * Adding a food.
 *
 * The quantity defaults to one serving and the calories are shown *before* the
 * portion is committed, so choosing between 100g and 150g of rice is a glance
 * rather than an add-check-delete-retry loop.
 */
function AddPortion({ meal, foods, member }: { meal: number; foods: FoodItem[]; member?: number }) {
  const queryClient = useQueryClient();
  const [foodId, setFoodId] = useState<number | "">("");
  const [grams, setGrams] = useState("");
  const [query, setQuery] = useState("");

  const food = foods.find((f) => f.id === foodId);
  const shortlist = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return needle ? foods.filter((f) => f.name.toLowerCase().includes(needle)) : foods;
  }, [foods, query]);

  // The same arithmetic the server will do, so the preview and the saved row
  // agree: the catalogue is per 100g.
  const preview =
    food && Number(grams) > 0
      ? {
          calories: Math.round((Number(food.calories) * Number(grams)) / 100),
          protein: Math.round((Number(food.protein_g) * Number(grams)) / 100),
        }
      : null;

  const add = useMutation({
    mutationFn: () => addDietItem({ meal, food: foodId as number, quantity_g: grams }, member),
    onSuccess: () => {
      setFoodId("");
      setGrams("");
      setQuery("");
      queryClient.invalidateQueries({ queryKey: ["diet"] });
    },
  });

  function pick(id: number | "") {
    setFoodId(id);
    const picked = foods.find((f) => f.id === id);
    // One serving is what someone means by "add rice", not one gram.
    setGrams(picked?.serving_grams ? String(round(picked.serving_grams)) : "100");
  }

  const step = stepFor(food?.serving_grams ?? null);

  return (
    <div className="mt-2 rounded-md bg-[var(--color-surface-2)] p-2">
      <div className="flex flex-wrap gap-2">
        {/* Typing narrows a 44-item list far faster than scrolling it. */}
        <Input
          placeholder="Search food"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="w-[130px] py-1.5 text-sm"
        />
        <Select
          value={foodId}
          onChange={(e) => pick(Number(e.target.value) || "")}
          className="min-w-0 flex-1"
        >
          <option value="">{shortlist.length} foods</option>
          {shortlist.map((f) => (
            <option key={f.id} value={f.id}>
              {f.name}
            </option>
          ))}
        </Select>
      </div>

      {food && (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <span className="flex items-center gap-1">
            <button
              onClick={() => setGrams(String(Math.max(1, Number(grams) - step)))}
              className="h-7 w-7 rounded-md border border-[var(--color-border)] text-[var(--color-text-muted)] hover:border-[var(--color-accent)] hover:text-[var(--color-text)]"
              aria-label="Less"
            >
              -
            </button>
            <Input
              type="number"
              min={1}
              value={grams}
              onChange={(e) => setGrams(e.target.value)}
              className="w-[84px] px-2 py-1 text-center text-sm"
            />
            <button
              onClick={() => setGrams(String(Number(grams) + step))}
              className="h-7 w-7 rounded-md border border-[var(--color-border)] text-[var(--color-text-muted)] hover:border-[var(--color-accent)] hover:text-[var(--color-text)]"
              aria-label="More"
            >
              +
            </button>
            <span className="text-xs text-[var(--color-text-muted)]">g</span>
          </span>

          {preview && (
            <span className="text-xs text-[var(--color-text-muted)]">
              adds <b className="text-[var(--color-text)]">{preview.calories}</b> kcal ·{" "}
              {preview.protein}g protein
              {servingText(Number(grams), food.serving_label, food.serving_grams) &&
                ` · ${servingText(Number(grams), food.serving_label, food.serving_grams)}`}
            </span>
          )}

          <Button
            onClick={() => add.mutate()}
            disabled={!grams || add.isPending}
            className="ml-auto px-3 py-1 text-sm"
          >
            {add.isPending ? "Adding..." : "Add"}
          </Button>
        </div>
      )}
    </div>
  );
}

function MealBlock({
  meal,
  foods,
  member,
  target,
}: {
  meal: DietMeal;
  foods: FoodItem[];
  member?: number;
  target: number | null;
}) {
  const queryClient = useQueryClient();
  const remove = useMutation({
    mutationFn: () => deleteDietMeal(meal.id, member),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["diet"] }),
  });

  return (
    <div className="rounded-lg border border-[var(--color-border)] p-3">
      <div className="mb-1 flex flex-wrap items-baseline justify-between gap-2">
        <h4 className="text-sm font-semibold uppercase tracking-wide text-[var(--color-text)]">
          {meal.meal_type_name}
        </h4>
        <span className="flex items-center gap-3">
          <MacroRow macros={meal.macros} />
          <button
            onClick={() => remove.mutate()}
            className={ghostButtonClass}
          >
            Remove meal
          </button>
        </span>
      </div>

      {meal.items.length === 0 ? (
        <p className="py-1 text-sm text-[var(--color-text-muted)]">Nothing in this meal yet.</p>
      ) : (
        <ul className="flex flex-col">
          {meal.items.map((item) => (
            <PortionRow key={item.id} item={item} member={member} target={target} />
          ))}
        </ul>
      )}

      <AddPortion meal={meal.id} foods={foods} member={member} />
    </div>
  );
}

/** The full editor for one day. Only one day is on screen at a time -- seven
 *  cards of meals side by side is what made this hard to read. */
function DayEditor({
  weekday,
  day,
  plan,
  foods,
  member,
}: {
  weekday: number;
  day: DietDay | undefined;
  plan: DietPlan;
  foods: FoodItem[];
  member?: number;
}) {
  const queryClient = useQueryClient();
  const [label, setLabel] = useState("");
  const [mealType, setMealType] = useState<string>(MEAL_TYPES[0].value);
  const [error, setError] = useState("");

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["diet"] });

  const createDay = useMutation({
    mutationFn: () => addDietDay({ plan: plan.id, weekday, label }, member),
    onSuccess: () => {
      setLabel("");
      setError("");
      refresh();
    },
    onError: () => setError("Could not add that day."),
  });
  const removeDay = useMutation({
    mutationFn: () => deleteDietDay(day!.id, member),
    onSuccess: refresh,
  });
  const createMeal = useMutation({
    mutationFn: () => addDietMeal({ day: day!.id, meal_type: mealType }, member),
    onSuccess: () => {
      setError("");
      refresh();
    },
    onError: () => setError("That meal is already on this day."),
  });

  if (!day) {
    return (
      <Card accent="var(--color-border)">
        <h3 className="font-display text-2xl text-[var(--color-text)]">{WEEKDAYS[weekday]}</h3>
        <p className="mt-1 mb-4 text-sm text-[var(--color-text-muted)]">
          Nothing planned for this day yet.
        </p>
        <div className="flex flex-wrap gap-2">
          <Input
            placeholder="Name this day (optional) — e.g. Training day"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            className="min-w-[220px] flex-1"
          />
          <Button onClick={() => createDay.mutate()} disabled={createDay.isPending}>
            {createDay.isPending ? "Adding..." : "Plan this day"}
          </Button>
        </div>
        <ErrorText>{error}</ErrorText>
      </Card>
    );
  }

  const kcal = round(day.macros.calories);
  // A meal type can only appear once a day, so already-used ones drop out of
  // the picker instead of failing on save.
  const used = new Set(day.meals.map((m) => m.meal_type));
  const available = MEAL_TYPES.filter((m) => !used.has(m.value));

  return (
    <Card accent="var(--color-accent)">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="font-display text-2xl leading-none text-[var(--color-text)]">
            {WEEKDAYS[weekday]}
          </h3>
          <p className="mt-1 text-sm text-[var(--color-text-muted)]">{day.display_label}</p>
        </div>
        <div className="text-right">
          <p className="font-display text-3xl leading-none text-[var(--color-accent)]">{kcal}</p>
          <p className="text-[10px] uppercase tracking-wide text-[var(--color-text-muted)]">
            kcal this day
          </p>
        </div>
      </div>

      <div className="mb-4">
        <MacroRow macros={day.macros} className="mb-2 block" />
        <TargetBar kcal={kcal} target={plan.target_calories} />
      </div>

      {day.meals.length === 0 ? (
        <EmptyState>No meals yet. Add one below.</EmptyState>
      ) : (
        <div className="flex flex-col gap-3">
          {day.meals.map((meal) => (
            <MealBlock
              key={meal.id}
              meal={meal}
              foods={foods}
              member={member}
              target={plan.target_calories}
            />
          ))}
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-[var(--color-border)] pt-3">
        {available.length > 0 ? (
          <>
            <Select
              value={mealType}
              onChange={(e) => setMealType(e.target.value)}
              className="max-w-[220px]"
            >
              {available.map((m) => (
                <option key={m.value} value={m.value}>
                  {m.label}
                </option>
              ))}
            </Select>
            <Button variant="secondary" onClick={() => createMeal.mutate()} disabled={createMeal.isPending}>
              Add meal
            </Button>
          </>
        ) : (
          <span className="text-sm text-[var(--color-text-muted)]">
            Every meal slot on this day is used.
          </span>
        )}
        <button
          onClick={() => removeDay.mutate()}
          className={`${ghostButtonClass} ml-auto`}
        >
          Clear this day
        </button>
        <ErrorText>{error}</ErrorText>
      </div>
    </Card>
  );
}

/**
 * The whole weekly diet planner. Passing `member` points every read and write
 * at that member instead of the signed-in user, which is how a trainer writes
 * a plan for one of their people without a second copy of this screen.
 */
export default function DietPlanner({ member }: { member?: number }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState("My diet plan");
  const [goal, setGoal] = useState<DietGoal>("maintain");
  const [target, setTarget] = useState("");
  // Null until someone picks a day, so the default can follow the plan
  // rather than being frozen at mount before the plan has loaded.
  const [selected, setSelected] = useState<number | null>(null);

  const { data: plans, isLoading, isError } = useQuery({
    queryKey: ["diet", "plans", member ?? "me"],
    queryFn: () => fetchDietPlans(member),
  });
  const { data: foods } = useQuery({ queryKey: ["diet", "foods"], queryFn: () => fetchFoods() });

  const start = useMutation({
    mutationFn: () =>
      createDietPlan(
        { name, goal, target_calories: target ? Number(target) : null },
        member
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["diet"] }),
  });

  const plan = plans?.find((p) => p.is_active);

  const byWeekday = useMemo(() => {
    const map = new Map<number, DietDay>();
    plan?.days.forEach((d) => map.set(d.weekday, d));
    return map;
  }, [plan]);

  const today = todayWeekday();
  // Land on today when it's planned; otherwise on the first day that is, so a
  // member who trains four days a week doesn't open the page onto an empty
  // Sunday and think nothing is set up.
  const firstPlanned = plan?.days.length
    ? Math.min(...plan.days.map((d) => d.weekday))
    : today;
  const shown = selected ?? (byWeekday.has(today) ? today : firstPlanned);
  const dailyCalories = plan ? round(plan.daily_macros.calories) : 0;

  if (isLoading) {
    return (
      <Card>
        <LoadingState />
      </Card>
    );
  }
  if (isError) {
    return (
      <Card>
        <ErrorState />
      </Card>
    );
  }

  if (!plan) {
    return (
      <Card accent={railColor(0)}>
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          Set up the diet plan
        </h2>
        <p className="mb-4 max-w-prose text-sm text-[var(--color-text-muted)]">
          Name the plan and set a daily calorie target if there is one. Any day left empty simply
          has nothing planned, so a four-day plan just means filling in four days.
        </p>
        <div className="flex flex-wrap gap-3">
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="max-w-xs"
            placeholder="Plan name"
          />
          <Select
            value={goal}
            onChange={(e) => setGoal(e.target.value as DietGoal)}
            className="max-w-[180px]"
          >
            {DIET_GOALS.map((g) => (
              <option key={g.value} value={g.value}>
                {g.label}
              </option>
            ))}
          </Select>
          <Input
            type="number"
            min={0}
            placeholder="Target kcal/day"
            value={target}
            onChange={(e) => setTarget(e.target.value)}
            className="max-w-[160px]"
          />
          <Button onClick={() => start.mutate()} disabled={!name || start.isPending}>
            {start.isPending ? "Creating..." : "Create plan"}
          </Button>
        </div>
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-5">
      <Card accent={railColor(0)}>
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h2 className="font-display text-2xl text-[var(--color-text)]">{plan.name}</h2>
            <p className="text-sm text-[var(--color-text-muted)]">
              {plan.goal_name} · {plan.days_planned} {plan.days_planned === 1 ? "day" : "days"}{" "}
              planned
              {plan.created_by_name ? ` · written by ${plan.created_by_name}` : ""}
            </p>
          </div>
          <div className="text-right">
            <p className="font-display text-3xl leading-none text-[var(--color-accent)]">
              {dailyCalories}
            </p>
            <p className="text-[11px] uppercase tracking-wide text-[var(--color-text-muted)]">
              kcal a day on average
            </p>
          </div>
        </div>
        <div className="mt-3 border-t border-[var(--color-border)] pt-3">
          <MacroRow macros={plan.daily_macros} className="mb-2 block" />
          <TargetBar kcal={dailyCalories} target={plan.target_calories} />
        </div>
      </Card>

      {/* The week at a glance: which days are planned, and what each comes to.
          Picking one opens it below rather than adding another wall of meals.

          Coloured like the exercise library's muscle cards -- a blurred blob in
          the corner and a soft diagonal fade. The colour is per weekday and
          carries meaning rather than being decoration: a day with no plan stays
          flat and grey, so "which days am I actually eating to?" is answerable
          without reading a word. */}
      <div className="no-scrollbar -mx-1 flex gap-2 overflow-x-auto px-1 pb-2 pt-1">
        {WEEKDAYS.map((label, weekday) => {
          const day = byWeekday.get(weekday);
          const active = weekday === shown;
          const colour = railColor(weekday);
          const planned = Boolean(day);
          return (
            <motion.button
              key={label}
              onClick={() => setSelected(weekday)}
              whileHover={{ y: -3 }}
              whileTap={{ scale: 0.97 }}
              transition={{ type: "spring", stiffness: 400, damping: 28 }}
              className="relative min-w-[104px] flex-1 overflow-hidden rounded-xl border px-3 py-2.5 text-left transition-colors"
              style={{
                borderColor: active && planned ? colour : "var(--color-border)",
                background: planned
                  ? `linear-gradient(135deg, ${colour}${active ? "33" : "1a"}, var(--color-surface))`
                  : "var(--color-surface)",
                boxShadow:
                  active && planned
                    ? `0 0 0 1px ${colour}, 0 8px 24px -10px ${colour}99`
                    : active
                      ? "0 0 0 1px var(--color-text-muted)"
                      : "none",
              }}
            >
              {planned && (
                <span
                  className="pointer-events-none absolute -right-5 -top-5 h-16 w-16 rounded-full blur-xl"
                  style={{ background: colour, opacity: active ? 0.4 : 0.22 }}
                />
              )}

              <span className="relative block text-xs font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
                {label.slice(0, 3)}
                {weekday === today && (
                  <span className="ml-1 text-[var(--color-accent)]">today</span>
                )}
              </span>
              <span
                className="relative block font-display text-xl leading-tight"
                style={{ color: planned ? colour : "var(--color-text-muted)" }}
              >
                {day ? round(day.macros.calories) : "—"}
              </span>
              <span className="relative block truncate text-[10px] text-[var(--color-text-muted)]">
                {day ? day.display_label : "not planned"}
              </span>
            </motion.button>
          );
        })}
      </div>

      {!foods?.length && (
        <EmptyState>
          The food catalogue is empty, so there is nothing to add to a meal yet.
        </EmptyState>
      )}

      <DayEditor
        // Remounting per day clears any half-typed portion when the day changes.
        key={shown}
        weekday={shown}
        day={byWeekday.get(shown)}
        plan={plan}
        foods={foods ?? []}
        member={member}
      />
    </div>
  );
}
