# services/admin.py

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from .models import ServiceCategory, Service, ServicePlan, Case, Document, Payment # Added Payment

# --- 1. Inline Registration for Plans ---
# This allows you to add/edit Service Plans (tiers) directly inside the Service form.
class ServicePlanInline(admin.TabularInline):
    model = ServicePlan
    extra = 1
    # Ensure fields related to pricing tiers are visible
    fields = ('name', 'price', 'features', 'is_recommended') 

# --- 2. Inline Registration for Services (Inside Category) ---
# This allows you to add/edit Services directly inside the ServiceCategory form.
class ServiceInline(admin.TabularInline):
    model = Service
    extra = 1
    show_change_link = True # Allows easy navigation to edit Service and its Plans

@admin.register(ServiceCategory)
class ServiceCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'description', 'detail_description')
    inlines = [ServiceInline]
    search_fields = ['name']

# --- 3. Service Registration (Updated for Plans) ---
@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    # 'price' field is removed from list_display as it is now in the Plan
    list_display = ('name', 'category', 'is_active') 
    list_filter = ('category', 'is_active')
    search_fields = ['name', 'description']
    inlines = [ServicePlanInline] # <-- Includes plans as an inline

# --- 4. Service Plan Registration ---
@admin.register(ServicePlan)
class ServicePlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'service', 'price', 'is_recommended')
    list_filter = ('service__category', 'service', 'is_recommended')
    search_fields = ['name', 'service__name']

# --- 5. Document Registration ---
@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ('document_type', 'case_link', 'uploaded_by', 'is_verified', 'uploaded_at')
    list_filter = ('is_verified', 'document_type')
    search_fields = ['document_type', 'case__id', 'uploaded_by__email']
    readonly_fields = ('uploaded_by', 'uploaded_at', 'file', 'case_link')
    
    def case_link(self, obj):
        # Create a link to the related Case object
        if obj.case:
            return format_html('<a href="{}">Case #{}</a>',
                               reverse("admin:services_case_change", args=(obj.case.id,)),
                               obj.case.id)
        return "No Case"
    case_link.short_description = 'Case'

# --- 6. NEW Payment Admin (Phase 4) ---
@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'case_link', 'amount', 'transaction_id', 'is_successful', 'paid_at')
    list_filter = ('is_successful', 'paid_at')
    search_fields = ['case__id', 'transaction_id']
    readonly_fields = ('case', 'amount', 'transaction_id', 'paid_at')
    
    def case_link(self, obj):
        # Link back to the case detail page
        return format_html('<a href="{}">Case #{}</a>',
                           reverse("admin:services_case_change", args=(obj.case.id,)),
                           obj.case.id)
    case_link.short_description = 'Case'
    
# --- 7. UPDATED Case Registration (Phase 4) ---
@admin.register(Case)
class CaseAdmin(admin.ModelAdmin):
    # Added 'payment_status' to the display
    list_display = ('id', 'client_email', 'service_plan_name', 'status', 'payment_status', 'assigned_staff', 'created_at')
    list_filter = ('status', 'service_plan__service__category', 'assigned_staff')
    search_fields = ['client__email', 'service_plan__service__name', 'id']
    readonly_fields = ('client', 'created_at', 'updated_at')
    
    fieldsets = (
        (None, {
            'fields': ('service_plan', 'client', 'status') # 'service' changed to 'service_plan'
        }),
        ('Staff Management', {
            'fields': ('assigned_staff',),
            'description': 'Assign this case to a staff member.'
        }),
    )
    
    # Custom methods updated for 'service_plan'
    def client_email(self, obj):
        return obj.client.email
    client_email.short_description = 'Client Email'

    def service_plan_name(self, obj):
        # Displays the name of the plan purchased (e.g., 'Proprietorship - Assured')
        return f"{obj.service_plan.service.name} - {obj.service_plan.name}"
    service_plan_name.short_description = 'Service Plan'

    # NEW method to show payment status in the list
    def payment_status(self, obj):
        try:
            if obj.payment.is_successful:
                return "PAID"
            return "FAILED"
        except Payment.DoesNotExist:
            return "UNPAID"
    payment_status.short_description = 'Payment Status'
