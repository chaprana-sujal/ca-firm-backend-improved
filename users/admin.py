from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser 

class CustomUserAdmin(UserAdmin):
    # 1. Add custom fields to the main list display
    list_display = ('email', 'first_name', 'last_name', 'is_ca_firm', 'is_staff')
    
    # 2. Add custom fields to the fields filter
    list_filter = ('is_ca_firm', 'is_staff', 'is_superuser', 'is_active')

    # 3. Define the fieldsets (groups of fields) for the User *CHANGE* page
    # This is the fix for your 500 Error.
    # We remove 'password' from this tuple.
    fieldsets = (
        (None, {'fields': ('email',)}),  # <-- 'password' REMOVED
        ('Personal Info', {'fields': ('first_name', 'last_name')}),
        ('Permissions', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        ('Custom Roles', {'fields': ('is_ca_firm',)}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )

    # 4. NEW: Define fieldsets for the User *ADD* page
    # This is required when extending UserAdmin and fixes the *next* error.
    # This is where 'password' belongs.
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password', 'password2'), # Use 'email' instead of 'username'
        }),
    )
    
    # 5. Define fields used for searching
    search_fields = ('email', 'first_name', 'last_name')
    
    # 6. Define fields used when creating a user from the Admin
    ordering = ('email',)

# Register the CustomUser model with our custom Admin class
admin.site.register(CustomUser, CustomUserAdmin)