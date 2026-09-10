from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from core.permissions import IsAdminOrReadOnly

from .models import Instructor
from .serializers import InstructorSerializer


class InstructorViewSet(ModelViewSet):

    def get_queryset(self):
        # Built per request, not at import: the scoped manager needs a
        # tenant in scope and a class attribute is evaluated on load.
        return Instructor.objects.select_related("user")
    serializer_class = InstructorSerializer
    permission_classes = [IsAdminOrReadOnly]

    @action(detail=False, methods=["get", "patch"], permission_classes=[IsAuthenticated])
    def me(self, request):
        """A trainer's own profile -- the one instructor record they may edit
        without being an admin."""
        profile = Instructor.objects.filter(user=request.user).first()
        if not profile:
            return Response({"detail": "No instructor profile for this account."}, status=404)
        if request.method == "PATCH":
            serializer = self.get_serializer(profile, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            # Guard the fields that decide *who* this profile belongs to and
            # whether it is publicly listed -- those stay admin-only.
            serializer.save(user=profile.user, active=profile.active)
            return Response(serializer.data)
        return Response(self.get_serializer(profile).data)
