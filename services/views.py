# services/views.py

from rest_framework import viewsets, permissions, generics, parsers
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.utils import timezone
# Import all models, including the new Payment model
from .models import ServiceCategory, Service, ServicePlan, Case, Document, Payment
from .serializers import (
    ServiceCategorySerializer, ServiceSerializer, ServicePlanSerializer, 
    CaseSerializer, CaseCreateSerializer, DocumentSerializer,
    PaymentSerializer, CaseStatusUpdateSerializer # Added Phase 4 serializers
)
from .permissions import IsCAFirm, IsClient, IsOwnerOrReadOnly
from .utils import send_status_update_email # Added Phase 4 email utility

# --- Phase 3 ViewSet (Unchanged) ---
class ServicePlanViewSet(viewsets.ModelViewSet):
    """
    API endpoint for CA Firm staff to CREATE, RETRIEVE, UPDATE, or DELETE 
    pricing plans associated with a service.
    """
    queryset = ServicePlan.objects.all()
    serializer_class = ServicePlanSerializer
    permission_classes = [IsCAFirm] # Only CA Firm staff can manage plans

# --- Phase 3 ViewSet (Unchanged) ---
class ServiceCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for the UI navigation menu.
    Updated to prefetch plans for efficiency.
    """
    queryset = ServiceCategory.objects.prefetch_related('services__plans').filter(services__is_active=True).distinct()
    serializer_class = ServiceCategorySerializer
    permission_classes = [permissions.IsAuthenticated]

# --- Phase 3 ViewSet (Unchanged) ---
class ServiceViewSet(viewsets.ModelViewSet):
    """
    API endpoint for CA Firm Admins to CREATE/UPDATE individual services.
    """
    queryset = Service.objects.prefetch_related('plans').all() 
    serializer_class = ServiceSerializer
    permission_classes = [IsCAFirm]

# --- Case ViewSet (Updated for Phase 4) ---
class CaseViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing Cases.
    - Clients can create and list their own cases.
    - CA Staff can list all cases and update any case status.
    """
    def get_queryset(self):
        user = self.request.user
        # Updated to prefetch 'payment' relationship for efficiency
        if user.is_ca_firm:
            return Case.objects.select_related(
                'client', 'service_plan__service', 'payment'
            ).prefetch_related('documents').all()
        
        # Clients can only see their own cases
        return Case.objects.filter(client=user).select_related(
            'service_plan__service', 'payment'
        ).prefetch_related('documents')

    def get_serializer_class(self):
        if self.action == 'create':
            return CaseCreateSerializer
        # Use CaseStatusUpdateSerializer for PATCH/PUT actions
        if self.action in ['update', 'partial_update']:
             return CaseStatusUpdateSerializer
        return CaseSerializer # Returns full Case details

    def get_permissions(self):
        """ Instantiates and returns the list of permissions. """
        if self.action == 'create':
            self.permission_classes = [IsClient]
        elif self.action in ['update', 'partial_update']:
            # Only CA staff can update status
            self.permission_classes = [IsCAFirm]
        elif self.action == 'destroy':
            self.permission_classes = [IsCAFirm]
        else:
            # List, Retrieve
            self.permission_classes = [permissions.IsAuthenticated]
        return super().get_permissions()

    def perform_create(self, serializer):
        serializer.save(client=self.request.user)

    def perform_update(self, serializer):
        with transaction.atomic():
            case = serializer.save()
            # Send notification if status changed
            if 'status' in serializer.validated_data:
                send_status_update_email(case)

# --- Phase 3 View (Unchanged) ---
class DocumentUploadView(generics.CreateAPIView):
    """
    API endpoint for securely uploading a document related to a specific case.
    POST /api/cases/<pk>/documents/upload/
    """
    queryset = Document.objects.all()
    serializer_class = DocumentSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = (parsers.MultiPartParser, parsers.FormParser) 

    def perform_create(self, serializer):
        case_id = self.kwargs.get('pk') 
        case = get_object_or_404(Case, pk=case_id)

        if case.client != self.request.user and not self.request.user.is_ca_firm:
            raise permissions.PermissionDenied("You do not have permission to upload documents for this case.")

        serializer.save(
            case=case,
            uploaded_by=self.request.user,
            is_verified=self.request.user.is_ca_firm 
        )

# --- NEW Phase 4 Views ---

class PaymentCreateView(generics.CreateAPIView):
    """
    API endpoint to simulate successful payment for a PENDING case.
    Creates a Payment record and automatically updates Case status to PAID.
    POST /api/cases/<pk>/pay/
    """
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer # We only use this for output
    permission_classes = [IsClient] # Only the client can pay

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        case_id = self.kwargs.get('pk')
        case = get_object_or_404(Case, pk=case_id)

        # 1. Validation Checks
        if case.client != request.user:
            return Response({"detail": "Case does not belong to the authenticated client."}, status=status.HTTP_403_FORBIDDEN)
        if case.status != Case.CaseStatus.PENDING:
            return Response({"detail": f"Case is not in 'Waiting for Payment' state. Current status: {case.get_status_display()}"}, status=status.HTTP_400_BAD_REQUEST)
        if hasattr(case, 'payment') and case.payment.is_successful:
            return Response({"detail": "Payment already processed for this case."}, status=status.HTTP_400_BAD_REQUEST)

        # 2. Simulate Payment Creation
        payment, created = Payment.objects.update_or_create(
            case=case,
            defaults={
                'amount': case.service_plan.price,
                'transaction_id': f"SIMULATED_{case.id}_{int(timezone.now().timestamp())}",
                'is_successful': True,
                'paid_at': timezone.now()
            }
        )

        # 3. Update Case Status to PAID
        case.status = Case.CaseStatus.PAID
        case.save()

        # 4. Send Confirmation Email
        send_status_update_email(case)
        
        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)

class CaseStatusUpdateView(generics.UpdateAPIView):
    """
    API endpoint for CA Firm Staff to update the status and assign staff for a case.
    PATCH /api/cases/<pk>/status/
    """
    queryset = Case.objects.all()
    serializer_class = CaseStatusUpdateSerializer
    permission_classes = [IsCAFirm] # Only CA Firm staff can change status

    def perform_update(self, serializer):
        with transaction.atomic():
            case = serializer.save()
            
            # Send notification if status changed
            if 'status' in serializer.validated_data:
                send_status_update_email(case)