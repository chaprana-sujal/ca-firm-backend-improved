# services/serializers.py
from rest_framework import serializers
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import ServiceCategory, Service, ServicePlan, Case, Document, Payment

# --- PHASE 3/4 SERIALIZERS ---

class DocumentSerializer(serializers.ModelSerializer):
    uploaded_by_email = serializers.ReadOnlyField(source='uploaded_by.email')
    class Meta:
        model = Document
        fields = ('id', 'case', 'file', 'document_type', 'uploaded_by_email', 'uploaded_at', 'is_verified')
        read_only_fields = ('uploaded_by_email', 'uploaded_at', 'is_verified')

class ServicePlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServicePlan
        fields = ('id', 'name', 'price', 'features', 'is_recommended')

class ServiceSerializer(serializers.ModelSerializer):
    plans = ServicePlanSerializer(many=True, read_only=True)
    class Meta:
        model = Service
        fields = ('id', 'name', 'description', 'is_active', 'category', 'plans', 'features', 'requirements', 'deliverables', 'timeline', 'icon') 

class ServiceCategorySerializer(serializers.ModelSerializer):
    services = ServiceSerializer(many=True, read_only=True)
    class Meta:
        model = ServiceCategory
        fields = ('id', 'name', 'description', 'services', 'icon')

class PaymentSerializer(serializers.ModelSerializer):
    case_id = serializers.ReadOnlyField(source='case.id')
    class Meta:
        model = Payment
        fields = ('case_id', 'amount', 'transaction_id', 'is_successful', 'paid_at')

# --- CASE SERIALIZERS ---

class CaseSerializer(serializers.ModelSerializer):
    client = serializers.StringRelatedField(read_only=True) 
    service_plan = ServicePlanSerializer(read_only=True) 
    documents = DocumentSerializer(many=True, read_only=True) 
    payment = PaymentSerializer(read_only=True) 
    
    # This will correctly show the assigned staff's email or string representation
    assigned_staff = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = Case
        fields = (
            'id', 'client', 'service_plan', 'assigned_staff', 'status', 
            'created_at', 'updated_at', 'documents', 'payment'
        )
        read_only_fields = ('client', 'assigned_staff', 'created_at', 'updated_at', 'payment')

class CaseCreateSerializer(serializers.ModelSerializer):
    service_plan = serializers.PrimaryKeyRelatedField(queryset=ServicePlan.objects.all())
    class Meta:
        model = Case
        fields = ('id', 'service_plan', 'status') 
        read_only_fields = ('id', 'status') 

    def create(self, validated_data):
        client_user = self.context['request'].user
        case = Case.objects.create(
            client=client_user,
            service_plan=validated_data['service_plan'],
            status=Case.CaseStatus.PENDING
        )
        return case

class CaseStatusUpdateSerializer(serializers.ModelSerializer):
    """
    Used for PATCH /api/cases/<pk>/.
    FIX: This is the robust solution that solves startup crashes and response crashes.
    """
    status = serializers.ChoiceField(choices=Case.CaseStatus.choices, required=False)
    
    # We accept a simple Integer ID for writing (input)
    assigned_staff_id = serializers.IntegerField(
        allow_null=True, required=False, write_only=True
    )
    
    # We show the string representation for reading (output)
    assigned_staff = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = Case
        fields = ('status', 'assigned_staff', 'assigned_staff_id')
        read_only_fields = ('assigned_staff',) # assigned_staff is for output only
    
    def validate_assigned_staff_id(self, staff_id):
        """
        This method runs ONLY during validation (when you hit Send), 
        not during startup.
        """
        if staff_id is None:
            return None
        
        User = get_user_model()
        try:
            # Manually run the check that was failing
            staff_user = User.objects.get(pk=staff_id, is_ca_firm=True)
        except User.DoesNotExist:
            # This will now correctly raise the "Invalid pk" error
            raise serializers.ValidationError(f"Invalid pk \"{staff_id}\" - object does not exist or is not a staff member.")
        
        # Return the valid user object
        return staff_user

    def validate_status(self, value):
        instance = self.instance
        if instance.status == Case.CaseStatus.PENDING and value != Case.CaseStatus.PAID:
            if not hasattr(instance, 'payment') or not instance.payment.is_successful:
                raise serializers.ValidationError("Case must be marked as PAID before setting status to anything other than PAID.")
        if instance.status == Case.CaseStatus.COMPLETED and value != Case.CaseStatus.COMPLETED:
            raise serializers.ValidationError("Completed cases cannot be reopened.")
        return value

    def update(self, instance, validated_data):
        """
        Manually handle saving the assigned_staff object.
        """
        # Pop the staff *object* we validated from the data.
        staff_object = validated_data.pop('assigned_staff_id', None)
        
        # If a staff ID was provided, assign the object.
        if staff_object is not None:
            instance.assigned_staff = staff_object
        
        # Let the default update method handle the rest (like 'status')
        instance = super().update(instance, validated_data)
        instance.save()
        return instance

