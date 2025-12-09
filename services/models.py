from django.db import models
from django.conf import settings
from django.utils import timezone # Added for use in Payment model logic
from django.core.validators import FileExtensionValidator

# --- PHASE 2 MODELS ---

class ServiceCategory(models.Model):
    """
    The main service categories, e.g., "Startup", "GST", "Trademark". (Level 1 Hierarchy)
    """
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True, null=True)
    icon = models.CharField(max_length=10, default="📂", help_text="Emoji icon")
    
    class Meta:
        verbose_name_plural = "Service Categories"

    def __str__(self):
        return self.name

class Service(models.Model):
    """
    A specific service offered by the CA firm, e.g., "Proprietorship Registration".
    The pricing complexity is handled by related ServicePlan models.
    """
    category = models.ForeignKey(
        ServiceCategory, 
        related_name='services', 
        on_delete=models.CASCADE
    )
    name = models.CharField(max_length=255)
    description = models.TextField()
    is_active = models.BooleanField(default=True)
    features = models.TextField(help_text="Line-separated list of features", blank=True, default="")
    requirements = models.TextField(help_text="Line-separated list of required documents", blank=True, default="")
    deliverables = models.TextField(help_text="Line-separated list of deliverables", blank=True, default="")
    timeline = models.CharField(max_length=100, blank=True, default="3-5 working days")
    icon = models.CharField(max_length=10, default="📋", help_text="Emoji icon")

    def __str__(self):
        return f"{self.category.name} - {self.name}"

# --- PHASE 3 MODELS ---

class ServicePlan(models.Model):
    """
    Tiered pricing and features for a Service (e.g., Basic, Assured, Compliance).
    """
    service = models.ForeignKey(
        Service, 
        related_name='plans', 
        on_delete=models.CASCADE
    )
    name = models.CharField(max_length=100) # e.g., 'Basic', 'Most Popular'
    price = models.DecimalField(max_digits=10, decimal_places=2)
    features = models.TextField(
        help_text="Bullet points describing what is included in this plan."
    )
    is_recommended = models.BooleanField(default=False) # For UI highlighting

    class Meta:
        unique_together = ('service', 'name')
        ordering = ['price']

    def __str__(self):
        return f"{self.service.name} - {self.name} ({self.price})"

class Document(models.Model):
    """
    Represents a file uploaded by the client or CA staff related to a case.
    """
    case = models.ForeignKey(
        'Case', 
        related_name='documents', 
        on_delete=models.CASCADE
    )
    file = models.FileField(
        upload_to='case_documents/%Y/%m/%d/', # Files saved to /app/media/case_documents/...
        validators=[FileExtensionValidator(allowed_extensions=['pdf', 'jpg', 'jpeg'])]
    )
    document_type = models.CharField(max_length=255) # e.g., "Aadhaar Card", "MOA Draft"
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.PROTECT
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    is_verified = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.document_type} for Case {self.case.id}"

# --- UPDATED CASE MODEL (Phase 4 Statuses) ---

class Case(models.Model):
    """
    An instance of a service plan purchased by a client.
    Status choices are expanded to enforce payment and workflow steps.
    """
    class CaseStatus(models.TextChoices):
        # Expanded Statuses for Workflow Enforcement
        PENDING = 'PENDING', 'Waiting for Payment'
        PAID = 'PAID', 'Payment Confirmed / Ready for Staff'
        IN_PROGRESS = 'IN_PROGRESS', 'Processing by Staff'
        NEEDS_DOCUMENTS = 'NEEDS_DOCUMENTS', 'Awaiting Client Documents'
        COMPLETED = 'COMPLETED', 'Case Filed & Closed'
        CANCELED = 'CANCELED', 'Canceled'

    client = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        related_name='cases', 
        on_delete=models.PROTECT,
        limit_choices_to={'is_ca_firm': False}
    )
    service_plan = models.ForeignKey(
        ServicePlan, 
        related_name='cases', 
        on_delete=models.PROTECT
    )
    assigned_staff = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='managed_cases',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={'is_ca_firm': True}
    )
    
    status = models.CharField(
        max_length=20, 
        choices=CaseStatus.choices, 
        default=CaseStatus.PENDING # Default to PENDING PAYMENT
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Case {self.id} ({self.service_plan.name}) for {self.client.email}"

# --- PHASE 4 MODEL ---

class Payment(models.Model):
    """
    Simulates a transaction record for a specific case.
    Uses OneToOneField to ensure only one payment per case.
    """
    case = models.OneToOneField(
        Case,
        related_name='payment',
        on_delete=models.CASCADE
    )
    amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        help_text="The amount charged (auto-populated from ServicePlan)."
    )
    transaction_id = models.CharField(
        max_length=255, 
        unique=True,
        blank=True,
        null=True,
        help_text="Unique ID from the payment gateway (simulated)."
    )
    is_successful = models.BooleanField(default=False)
    paid_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Payment for Case {self.case.id} - {'SUCCESS' if self.is_successful else 'PENDING'}"
