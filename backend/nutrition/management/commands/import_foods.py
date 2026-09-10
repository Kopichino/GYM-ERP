"""Seeds the food catalogue with everyday Indian gym food.

Values are per 100 g and rounded to what a nutrition label would print --
precise enough to plan against, and not pretending to lab accuracy. Run it
once; it skips foods that already exist so it is safe to re-run after adding
more rows below.
"""

from decimal import Decimal

from django.core.management.base import BaseCommand

from nutrition.models import FoodCategory, FoodItem

# name, category, kcal, protein, carbs, fat, serving label, serving grams
FOODS = [
    ("Roti (whole wheat)", FoodCategory.GRAIN, 297, 11.0, 58.0, 3.7, "1 roti", 40),
    ("Boiled rice", FoodCategory.GRAIN, 130, 2.7, 28.0, 0.3, "1 cup", 160),
    ("Brown rice", FoodCategory.GRAIN, 123, 2.7, 26.0, 1.0, "1 cup", 160),
    ("Oats (dry)", FoodCategory.GRAIN, 389, 16.9, 66.0, 6.9, "1 cup", 80),
    ("Poha (dry)", FoodCategory.GRAIN, 356, 6.6, 77.0, 1.2, "1 cup", 90),
    ("Whole wheat bread", FoodCategory.GRAIN, 247, 13.0, 41.0, 3.4, "1 slice", 30),
    ("Chapati flour (atta)", FoodCategory.GRAIN, 340, 12.0, 69.0, 1.7, "", None),
    ("Chicken breast (cooked)", FoodCategory.PROTEIN, 165, 31.0, 0.0, 3.6, "1 fillet", 120),
    ("Chicken thigh (cooked)", FoodCategory.PROTEIN, 209, 26.0, 0.0, 10.9, "1 piece", 90),
    ("Egg (whole)", FoodCategory.PROTEIN, 155, 13.0, 1.1, 11.0, "1 egg", 50),
    ("Egg white", FoodCategory.PROTEIN, 52, 11.0, 0.7, 0.2, "1 white", 33),
    ("Paneer", FoodCategory.PROTEIN, 265, 18.3, 1.2, 20.8, "1 cube", 25),
    ("Tofu", FoodCategory.PROTEIN, 76, 8.0, 1.9, 4.8, "1 slab", 100),
    ("Soya chunks (dry)", FoodCategory.PROTEIN, 345, 52.0, 33.0, 0.5, "1 cup", 60),
    ("Rajma (cooked)", FoodCategory.PROTEIN, 127, 8.7, 22.8, 0.5, "1 cup", 180),
    ("Chana / chickpeas (cooked)", FoodCategory.PROTEIN, 164, 8.9, 27.4, 2.6, "1 cup", 165),
    ("Toor dal (cooked)", FoodCategory.PROTEIN, 116, 7.0, 21.0, 0.4, "1 bowl", 200),
    ("Fish (rohu, cooked)", FoodCategory.PROTEIN, 97, 16.6, 0.0, 3.3, "1 piece", 100),
    ("Mutton (cooked)", FoodCategory.PROTEIN, 258, 25.6, 0.0, 16.5, "", None),
    ("Milk (toned)", FoodCategory.DAIRY, 58, 3.2, 4.7, 3.0, "1 glass", 240),
    ("Curd (plain)", FoodCategory.DAIRY, 61, 3.5, 4.7, 3.3, "1 bowl", 150),
    ("Greek yoghurt", FoodCategory.DAIRY, 59, 10.0, 3.6, 0.4, "1 cup", 170),
    ("Cheese slice", FoodCategory.DAIRY, 350, 22.0, 2.0, 28.0, "1 slice", 20),
    ("Spinach", FoodCategory.VEGETABLE, 23, 2.9, 3.6, 0.4, "1 cup", 30),
    ("Broccoli", FoodCategory.VEGETABLE, 34, 2.8, 6.6, 0.4, "1 cup", 90),
    ("Potato (boiled)", FoodCategory.VEGETABLE, 87, 1.9, 20.1, 0.1, "1 medium", 150),
    ("Sweet potato (boiled)", FoodCategory.VEGETABLE, 86, 1.6, 20.1, 0.1, "1 medium", 130),
    ("Cucumber", FoodCategory.VEGETABLE, 15, 0.7, 3.6, 0.1, "1 medium", 200),
    ("Tomato", FoodCategory.VEGETABLE, 18, 0.9, 3.9, 0.2, "1 medium", 120),
    ("Mixed salad", FoodCategory.VEGETABLE, 20, 1.2, 3.8, 0.2, "1 bowl", 100),
    ("Banana", FoodCategory.FRUIT, 89, 1.1, 22.8, 0.3, "1 medium", 120),
    ("Apple", FoodCategory.FRUIT, 52, 0.3, 13.8, 0.2, "1 medium", 180),
    ("Orange", FoodCategory.FRUIT, 47, 0.9, 11.8, 0.1, "1 medium", 130),
    ("Papaya", FoodCategory.FRUIT, 43, 0.5, 10.8, 0.3, "1 bowl", 150),
    ("Dates", FoodCategory.FRUIT, 277, 1.8, 75.0, 0.2, "1 date", 8),
    ("Ghee", FoodCategory.FAT, 900, 0.0, 0.0, 100.0, "1 tsp", 5),
    ("Groundnut oil", FoodCategory.FAT, 884, 0.0, 0.0, 100.0, "1 tsp", 5),
    ("Almonds", FoodCategory.FAT, 579, 21.2, 21.6, 49.9, "10 almonds", 12),
    ("Walnuts", FoodCategory.FAT, 654, 15.2, 13.7, 65.2, "4 halves", 15),
    ("Peanut butter", FoodCategory.FAT, 588, 25.1, 20.0, 50.4, "1 tbsp", 16),
    ("Coconut (fresh)", FoodCategory.FAT, 354, 3.3, 15.2, 33.5, "", None),
    ("Whey protein (powder)", FoodCategory.SUPPLEMENT, 400, 80.0, 8.0, 6.0, "1 scoop", 30),
    ("Mass gainer (powder)", FoodCategory.SUPPLEMENT, 380, 20.0, 68.0, 3.0, "1 scoop", 75),
    ("Creatine monohydrate", FoodCategory.SUPPLEMENT, 0, 0.0, 0.0, 0.0, "1 scoop", 5),
]


class Command(BaseCommand):
    help = "Load the starter food catalogue used by diet plans."

    def handle(self, *args, **options):
        created = 0
        for name, category, kcal, protein, carbs, fat, label, grams in FOODS:
            _, was_created = FoodItem.objects.get_or_create(
                name=name,
                defaults={
                    "category": category,
                    "calories": Decimal(kcal),
                    "protein_g": Decimal(str(protein)),
                    "carbs_g": Decimal(str(carbs)),
                    "fat_g": Decimal(str(fat)),
                    "serving_label": label,
                    "serving_grams": Decimal(grams) if grams else None,
                },
            )
            created += was_created

        self.stdout.write(
            self.style.SUCCESS(
                f"Food catalogue: {created} added, {FoodItem.objects.count()} total."
            )
        )
