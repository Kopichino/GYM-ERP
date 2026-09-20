from django.db.models import Q
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from core.permissions import access, IsOwnerOrAdmin, IsTenantMember

from .models import GalleryPost
from .serializers import GalleryPostSerializer


class IsUploaderOrAdmin(IsOwnerOrAdmin):
    owner_field = "uploader"


class GalleryPostViewSet(ModelViewSet):
    """Public feed = approved posts. Members also see their own pending
    uploads in their own list so they know it's awaiting moderation.
    Admins see everything and can approve via the extra action below."""

    serializer_class = GalleryPostSerializer
    permission_classes = [IsTenantMember, IsUploaderOrAdmin]

    def get_queryset(self):
        user = self.request.user
        qs = GalleryPost.objects.select_related("uploader")
        if access(self.request).is_admin:
            return qs
        return qs.filter(Q(approved=True) | Q(uploader=user))

    def perform_create(self, serializer):
        serializer.save(uploader=self.request.user)

    @action(detail=True, methods=["post"], permission_classes=[IsTenantMember])
    def approve(self, request, pk=None):
        if not access(request).is_admin:
            return Response({"detail": "Admins only."}, status=403)
        post = self.get_object()
        post.approved = True
        post.save(update_fields=["approved"])
        return Response(self.get_serializer(post).data)
