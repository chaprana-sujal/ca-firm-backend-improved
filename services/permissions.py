# services/permissions.py
from rest_framework import permissions

class IsCAFirm(permissions.BasePermission):
    """
    Allows access only to users who are CA Firm staff.
    """
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.is_ca_firm

class IsClient(permissions.BasePermission):
    """
    Allows access only to users who are Clients.
    """
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and not request.user.is_ca_firm

class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object to edit it,
    but allow read-only for others.
    """
    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to any request,
        # so we'll always allow GET, HEAD or OPTIONS requests.
        if request.method in permissions.SAFE_METHODS:
            return True

        # Write permissions are only allowed to the owner (client) of the case.
        # Or to any CA firm staff member.
        if hasattr(obj, 'client'):
            # This is a Case object
            return obj.client == request.user or request.user.is_ca_firm
        
        # Default to denying permission
        return False