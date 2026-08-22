from rest_framework.routers import DefaultRouter

from .views import GalleryPostViewSet

router = DefaultRouter()
router.register("", GalleryPostViewSet, basename="gallery-post")

urlpatterns = router.urls
