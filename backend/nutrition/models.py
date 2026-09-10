from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from tenancy.managers import TenantManager, UnscopedManager

from workouts.models import Weekday


class FoodCategory(models.TextChoices):
    GRAIN = "grain", "Grains & cereals"
    PROTEIN = "protein", "Protein"
    DAIRY = "dairy", "Dairy"
    VEGETABLE = "vegetable", "Vegetables"
    FRUIT = "fruit", "Fruit"
    FAT = "fat", "Fats & oils"
    SUPPLEMENT = "supplement", "Supplements"
    OTHER = "other", "Other"


class FoodItem(models.Model):
    """One line of the food catalogue, stored per 100 g.

    Everything is normalised to 100 g so a portion of any size is a single
    multiplication. Storing "calories per serving" alongside would let the two
    disagree the moment someone edited one of them.
    """

    name = models.CharField(max_length=120, unique=True)
    category = models.CharField(
        max_length=12, choices=FoodCategory.choices, default=FoodCategory.OTHER
    )
    calories = models.DecimalField(
        max_digits=7, decimal_places=2, validators=[MinValueValidator(0)], help_text="kcal per 100g"
    )
    protein_g = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    carbs_g = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    fat_g = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    # A household measure, so a member can be told "2 rotis" rather than "120g".
    serving_label = models.CharField(
        max_length=40, blank=True, help_text="e.g. 1 roti, 1 cup, 1 scoop."
    )
    serving_grams = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True, help_text="Grams in one serving."
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class DietGoal(models.TextChoices):
    CUT = "cut", "Fat loss"
    MAINTAIN = "maintain", "Maintenance"
    BULK = "bulk", "Muscle gain"


class DietPlan(models.Model):
    """A member's weekly eating plan.

    Shaped like the workout split on purpose: one active plan at a time, days
    pinned to weekdays, and every total derived from the items rather than
    stored. A member who already understands their split understands this.
    """
    # Logged in the context of one gym's programme, trainers and badges. A
    # member who trains at two gyms has a history at each; Gym A's sets must not
    # feed Gym B's leaderboards.
    tenant = models.ForeignKey(
        "tenancy.Tenant",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="diet_plans"
    )
    name = models.CharField(max_length=100, default="My diet plan")
    goal = models.CharField(max_length=10, choices=DietGoal.choices, default=DietGoal.MAINTAIN)
    # What the trainer is aiming for. The plan's actual calories are derived
    # from its meals, so the two together show whether the plan hits the target.
    target_calories = models.PositiveIntegerField(null=True, blank=True)
    target_protein_g = models.PositiveIntegerField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="diet_plans_written",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    #: Scoped to the branch that owns it; `.unscoped` is the way past
    #: this, and is deliberately awkward to type.
    tenant_field = "tenant"
    objects = TenantManager()
    unscoped = UnscopedManager()

    class Meta:
        ordering = ["-is_active", "-updated_at"]
        constraints = [
            # One current plan, so "what do I eat today?" has a single answer.
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(is_active=True),
                name="one_active_diet_plan_per_user",
            )
        ]

    @property
    def days_planned(self):
        return self.days.count()

    def __str__(self):
        return f"{self.user} - {self.name}"


class DietDay(models.Model):
    """One day of the plan, pinned to a weekday like the training split."""
    # Logged in the context of one gym's programme, trainers and badges. A
    # member who trains at two gyms has a history at each; Gym A's sets must not
    # feed Gym B's leaderboards.
    tenant = models.ForeignKey(
        "tenancy.Tenant",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )

    plan = models.ForeignKey(DietPlan, on_delete=models.CASCADE, related_name="days")
    weekday = models.PositiveSmallIntegerField(choices=Weekday.choices)
    label = models.CharField(
        max_length=60, blank=True, help_text="e.g. Training day, Rest day."
    )
    notes = models.TextField(blank=True)

    #: Scoped to the branch that owns it; `.unscoped` is the way past
    #: this, and is deliberately awkward to type.
    tenant_field = "tenant"
    objects = TenantManager()
    unscoped = UnscopedManager()

    class Meta:
        ordering = ["weekday"]
        constraints = [
            models.UniqueConstraint(fields=["plan", "weekday"], name="one_diet_day_per_weekday")
        ]

    @property
    def display_label(self):
        return self.label or "Eating plan"

    def __str__(self):
        return f"{self.get_weekday_display()} - {self.display_label}"


class MealType(models.TextChoices):
    BREAKFAST = "breakfast", "Breakfast"
    SNACK_AM = "snack_am", "Mid-morning snack"
    LUNCH = "lunch", "Lunch"
    SNACK_PM = "snack_pm", "Evening snack"
    DINNER = "dinner", "Dinner"
    PRE_WORKOUT = "pre_workout", "Pre-workout"
    POST_WORKOUT = "post_workout", "Post-workout"


class DietMeal(models.Model):
    """A sitting within a day. `order` decides the on-screen sequence, because
    a gym's idea of when the pre-workout meal falls is its own business."""
    # Logged in the context of one gym's programme, trainers and badges. A
    # member who trains at two gyms has a history at each; Gym A's sets must not
    # feed Gym B's leaderboards.
    tenant = models.ForeignKey(
        "tenancy.Tenant",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )

    day = models.ForeignKey(DietDay, on_delete=models.CASCADE, related_name="meals")
    meal_type = models.CharField(max_length=14, choices=MealType.choices)
    order = models.PositiveSmallIntegerField(default=0)
    notes = models.TextField(blank=True)

    #: Scoped to the branch that owns it; `.unscoped` is the way past
    #: this, and is deliberately awkward to type.
    tenant_field = "tenant"
    objects = TenantManager()
    unscoped = UnscopedManager()

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.day} - {self.get_meal_type_display()}"


class DietMealItem(models.Model):
    """A portion of one food inside a meal.

    Only the grams are stored. Calories and macros for the portion are worked
    out from the catalogue at read time, so correcting a food's macros fixes
    every plan that uses it instead of leaving stale numbers behind.
    """

    meal = models.ForeignKey(DietMeal, on_delete=models.CASCADE, related_name="items")
    food = models.ForeignKey(FoodItem, on_delete=models.PROTECT, related_name="meal_items")
    quantity_g = models.DecimalField(
        max_digits=7, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.quantity_g}g {self.food}"
