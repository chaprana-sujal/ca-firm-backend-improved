# services/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ServiceCategoryViewSet, 
    ServiceViewSet, 
    CaseViewSet, 
    DocumentUploadView, 
    ServicePlanViewSet,
    PaymentCreateView,      # <-- ADDED for Phase 4
    CaseStatusUpdateView    # <-- ADDED for Phase 4
)

# Create a router and register our viewsets with it.
router = DefaultRouter()

# Phase 2 ViewSets
router.register(r'service-categories', ServiceCategoryViewSet, basename='servicecategory')
router.register(r'services', ServiceViewSet, basename='service')
router.register(r'cases', CaseViewSet, basename='case')

# Phase 3 ViewSet
router.register(r'plans', ServicePlanViewSet, basename='plan') 

# The API URLs are now determined automatically by the router.
urlpatterns = [
    # Includes all router-generated URLs (services, plans, cases, etc.)
    path('', include(router.urls)),
    
    # Custom endpoint for file upload (from Phase 3)
    # POST /api/cases/123/documents/upload/
    path('cases/<int:pk>/documents/upload/', DocumentUploadView.as_view(), name='document_upload'),

    # --- NEW Phase 4 Endpoints ---

    # Custom endpoint for a Client to simulate payment
    # POST /api/cases/123/pay/
    path('cases/<int:pk>/pay/', PaymentCreateView.as_view(), name='case_pay'),
    
    # Custom endpoint for CA Staff to update status/assignment
    # PATCH /api/cases/123/status/
    path('cases/<int:pk>/status/', CaseStatusUpdateView.as_view(), name='case_status_update'),
]
