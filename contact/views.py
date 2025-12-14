from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.db import transaction
from .models import ConsultationRequest
from .serializers import ConsultationRequestSerializer
from .tasks import send_consultation_email_task

class ConsultationRequestView(generics.CreateAPIView):
    """
    API endpoint to handle free consultation form submissions.
    """
    queryset = ConsultationRequest.objects.all()
    serializer_class = ConsultationRequestSerializer
    permission_classes = [AllowAny]
    throttle_classes = []

    def perform_create(self, serializer):
        # improving: Capture IP address
        x_forwarded_for = self.request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = self.request.META.get('REMOTE_ADDR')
            
        instance = serializer.save(ip_address=ip)
        
        # Trigger the Celery task only after transaction commits
        transaction.on_commit(lambda: send_consultation_email_task.delay(instance.id))
