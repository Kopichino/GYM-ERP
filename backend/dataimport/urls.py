from django.urls import path

from .views import ImportCommitView, ImportPreviewView, ImportTemplateView

urlpatterns = [
    path("preview/", ImportPreviewView.as_view(), name="import-preview"),
    path("commit/", ImportCommitView.as_view(), name="import-commit"),
    path("template/<str:kind>/", ImportTemplateView.as_view(), name="import-template"),
]
