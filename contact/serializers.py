from rest_framework import serializers
from .models import ConsultationRequest

class ConsultationRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConsultationRequest
        fields = ['id', 'email', 'name', 'phone', 'service', 'created_at', 'ip_address']
        read_only_fields = ['created_at', 'ip_address']
