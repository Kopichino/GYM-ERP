from rest_framework.routers import DefaultRouter

from .views import ExpenseCategoryViewSet, ExpenseViewSet

router = DefaultRouter()
router.register("categories", ExpenseCategoryViewSet, basename="expense-category")
router.register("", ExpenseViewSet, basename="expense")

urlpatterns = router.urls
