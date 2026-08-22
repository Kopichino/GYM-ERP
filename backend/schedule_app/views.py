from rest_framework.viewsets import ModelViewSet

from core.permissions import IsAdminOrReadOnly

from .models import ClassSession
from .serializers import ClassSessionSerializer


class ClassSessionViewSet(ModelViewSet):
    queryset = ClassSession.objects.select_related("instructor")
    serializer_class = ClassSessionSerializer
    permission_classes = [IsAdminOrReadOnly]
