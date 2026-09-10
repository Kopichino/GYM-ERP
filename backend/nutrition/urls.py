from rest_framework.routers import DefaultRouter

from .views import (
    DietDayViewSet,
    DietMealItemViewSet,
    DietMealViewSet,
    DietPlanViewSet,
    FoodItemViewSet,
)

router = DefaultRouter()
router.register("foods", FoodItemViewSet, basename="fooditem")
router.register("plans", DietPlanViewSet, basename="dietplan")
router.register("days", DietDayViewSet, basename="dietday")
router.register("meals", DietMealViewSet, basename="dietmeal")
router.register("items", DietMealItemViewSet, basename="dietmealitem")

urlpatterns = router.urls
