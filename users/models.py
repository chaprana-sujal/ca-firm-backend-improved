from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from .managers import CustomUserManager

class CustomUser(AbstractBaseUser, PermissionsMixin):
    """
    Custom User Model using email as the unique identifier.
    Includes role fields for platform logic.
    """
    email = models.EmailField(unique=True)
    is_ca_firm = models.BooleanField(default=False, help_text='Designates whether the user is a CA Firm or a Client.')
    
    # Standard Django auth fields
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(auto_now_add=True)

    # Use email as the primary login field
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = [] # No required fields besides email/password

    objects = CustomUserManager()

    def __str__(self):
        return self.email

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()