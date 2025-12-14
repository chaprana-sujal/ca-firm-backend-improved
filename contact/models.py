from django.db import models

class ConsultationRequest(models.Model):
    """
    Model to store free consultation requests.
    """
    email = models.EmailField(help_text="Email address of the person requesting consultation")
    name = models.CharField(max_length=255, blank=True, null=True, help_text="Full Name of the person")
    phone = models.CharField(max_length=20, blank=True, null=True, help_text="Phone number")
    service = models.CharField(max_length=100, blank=True, null=True, help_text="Service interested in")
    created_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    is_processed = models.BooleanField(default=False, help_text="Whether this request has been addressed")

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Consultation Request'
        verbose_name_plural = 'Consultation Requests'

    def __str__(self):
        return f"{self.email} ({self.created_at.strftime('%Y-%m-%d %H:%M')})"
