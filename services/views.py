# services/views.py

from rest_framework import viewsets, permissions, generics, parsers
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.utils import timezone
from django.conf import settings
# Import all models, including the new Payment model
from .models import ServiceCategory, Service, ServicePlan, Case, Document, Payment
from .serializers import (
    ServiceCategorySerializer, ServiceSerializer, ServicePlanSerializer, 
    CaseSerializer, CaseCreateSerializer, DocumentSerializer,
    PaymentSerializer, CaseStatusUpdateSerializer # Added Phase 4 serializers
)
from .permissions import IsCAFirm, IsClient, IsOwnerOrReadOnly
from .utils import send_status_update_email # Added Phase 4 email utility
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
import razorpay
import hmac
import hashlib
import json
from razorpay import errors as razorpay_errors

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
    permission_classes = [AllowAny]

# --- Phase 3 ViewSet (Unchanged) ---
class ServiceViewSet(viewsets.ModelViewSet):
    """
    API endpoint for CA Firm Admins to CREATE/UPDATE individual services.
    """
    queryset = Service.objects.prefetch_related('plans').all() 
    serializer_class = ServiceSerializer
    permission_classes = [AllowAny]

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


class CreateRazorpayOrderView(APIView):
    """
    Create a Razorpay order for a PENDING case.
    POST /api/cases/<pk>/razorpay/create-order/
    Response contains `order_id`, `amount`, `currency`, and `key_id` for client checkout.
    """
    permission_classes = [IsClient]

    def post(self, request, pk, *args, **kwargs):
        case = get_object_or_404(Case, pk=pk)

        # Authorization and status checks
        if case.client != request.user:
            return Response({'detail': 'Case does not belong to the authenticated client.'}, status=status.HTTP_403_FORBIDDEN)
        if case.status != Case.CaseStatus.PENDING:
            return Response({'detail': 'Case is not awaiting payment.'}, status=status.HTTP_400_BAD_REQUEST)

        # Razorpay client
        key_id = settings.RAZORPAY_KEY_ID
        key_secret = settings.RAZORPAY_KEY_SECRET
        def _is_placeholder(val: str) -> bool:
            if not val:
                return True
            low = str(val).lower()
            # Treat obvious placeholders as not configured
            return ('your' in low) or ('change' in low) or ('example' in low) or (low.strip() in ('', 'key', 'secret', 'none', 'null'))

        # If Razorpay keys are not configured or are placeholder values, allow a DEBUG-only test flow
        if _is_placeholder(key_id) or _is_placeholder(key_secret):
            if settings.DEBUG:
                # Create a simulated order for local development/testing
                fake_order_id = f"TEST_ORDER_{case.id}_{int(timezone.now().timestamp())}"
                Payment.objects.update_or_create(
                    case=case,
                    defaults={
                        'amount': case.service_plan.price,
                        'transaction_id': fake_order_id,
                        'is_successful': False,
                    }
                )

                return Response({
                    'order_id': fake_order_id,
                    'amount': int(case.service_plan.price * 100),
                    'amount_rupees': str(case.service_plan.price),
                    'currency': 'INR',
                    'key_id': 'TEST_KEY',
                    'test_mode': True,
                })

            return Response({'detail': 'Payment gateway not configured.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        client = razorpay.Client(auth=(key_id, key_secret))

        amount_paise = int(case.service_plan.price * 100)
        order_data = {
            'amount': amount_paise,
            'currency': 'INR',
            'receipt': f'case_{case.id}',
            'notes': {
                'case_id': str(case.id),
                'client_email': case.client.email
            }
        }

        try:
            order = client.order.create(data=order_data)

            # Create a Payment record if not exists, store order id as transaction_id temporarily
            Payment.objects.update_or_create(
                case=case,
                defaults={
                    'amount': case.service_plan.price,
                    'transaction_id': order.get('id'),
                    'is_successful': False,
                }
            )

            return Response({
                'order_id': order.get('id'),
                'amount': order.get('amount'),
                'amount_rupees': str(case.service_plan.price),
                'currency': order.get('currency'),
                'key_id': key_id,
            })

        except razorpay_errors.AuthenticationError:
            return Response({'detail': 'Failed to create order: Authentication failed with payment gateway.'}, status=status.HTTP_401_UNAUTHORIZED)
        except (razorpay_errors.BadRequestError, razorpay_errors.ServerError) as e:
            return Response({'detail': f'Failed to create order: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'detail': f'Failed to create order: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class VerifyRazorpayPaymentView(APIView):
    """
    Verify payment signature from client after checkout and mark payment as successful.
    POST payload: { "razorpay_payment_id": "...", "razorpay_order_id": "...", "razorpay_signature": "..." }
    """
    permission_classes = [IsClient]

    def post(self, request, pk, *args, **kwargs):
        case = get_object_or_404(Case, pk=pk)

        if case.client != request.user:
            return Response({'detail': 'Case does not belong to the authenticated client.'}, status=status.HTTP_403_FORBIDDEN)

        data = request.data
        payment_id = data.get('razorpay_payment_id')
        order_id = data.get('razorpay_order_id')
        signature = data.get('razorpay_signature')

        if not all([payment_id, order_id, signature]):
            return Response({'detail': 'Missing payment verification parameters.'}, status=status.HTTP_400_BAD_REQUEST)

        secret = settings.RAZORPAY_KEY_SECRET

        # Treat placeholder secrets as not configured
        def _is_placeholder(val: str) -> bool:
            if not val:
                return True
            low = str(val).lower()
            return ('your' in low) or ('change' in low) or ('example' in low) or (low.strip() in ('', 'secret', 'none', 'null'))

        # If secret is a placeholder or missing, allow DEBUG-only verification via a 'test' flag
        if _is_placeholder(secret):
            if settings.DEBUG and (data.get('test') in [True, 'true', 'True']):
                # Accept the payment without HMAC verification (development only)
                pass
            else:
                return Response({'detail': 'Payment gateway not configured for verification.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        else:
            msg = f"{order_id}|{payment_id}".encode('utf-8')
            generated_signature = hmac.new(secret.encode('utf-8'), msg, hashlib.sha256).hexdigest()

            if not hmac.compare_digest(generated_signature, signature):
                return Response({'detail': 'Invalid signature.'}, status=status.HTTP_400_BAD_REQUEST)

        # Signature valid — mark payment successful
        payment, created = Payment.objects.update_or_create(
            case=case,
            defaults={
                'amount': case.service_plan.price,
                'transaction_id': payment_id,
                'is_successful': True,
                'paid_at': timezone.now()
            }
        )

        case.status = Case.CaseStatus.PAID
        case.save()

        # Notify asynchronously
        try:
            send_status_update_email(case)
        except Exception:
            pass

        return Response(PaymentSerializer(payment).data)


@method_decorator(csrf_exempt, name='dispatch')
class RazorpayWebhookView(APIView):
    """
    Endpoint to receive Razorpay webhooks. Public (AllowAny) but validates signature.
    POST /api/payments/razorpay/webhook/
    """
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        signature = request.META.get('HTTP_X_RAZORPAY_SIGNATURE')
        body = request.body
        secret = settings.RAZORPAY_KEY_SECRET

        if not signature or not secret:
            return Response({'detail': 'Webhook not configured.'}, status=status.HTTP_400_BAD_REQUEST)

        generated = hmac.new(secret.encode('utf-8'), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(generated, signature):
            return Response({'detail': 'Invalid webhook signature.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            payload = json.loads(body.decode('utf-8'))

            # Enqueue background processing and also update DB for common events
            from core.tasks import process_payment_webhook
            process_payment_webhook.delay(payload)

            # Attempt to update Payment for `payment.captured` events immediately
            event = payload.get('event')
            if event == 'payment.captured':
                payment_entity = payload.get('payload', {}).get('payment', {}).get('entity', {})
                payment_id = payment_entity.get('id')
                order_id = payment_entity.get('order_id')
                amount = payment_entity.get('amount')

                # Try to find Payment by transaction_id (order id stored earlier) or by order_id -> update
                try:
                    payment = Payment.objects.get(transaction_id=order_id)
                    payment.transaction_id = payment_id
                    payment.is_successful = True
                    payment.paid_at = timezone.now()
                    payment.save()

                    # Update case status
                    case = payment.case
                    case.status = Case.CaseStatus.PAID
                    case.save()
                    try:
                        send_status_update_email(case)
                    except Exception:
                        pass
                except Payment.DoesNotExist:
                    # No local payment found; ignore — background task may handle creating it
                    pass

            return Response({'status': 'ok'})

        except Exception as e:
            return Response({'detail': f'Webhook processing error: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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