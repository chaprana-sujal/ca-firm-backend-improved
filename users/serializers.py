from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.contrib.auth.password_validation import validate_password

CustomUser = get_user_model()

class RegistrationSerializer(serializers.ModelSerializer):
    """
    Serializer for new user registration. Handles validation and creation.
    """
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    password2 = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    
    class Meta:
        model = CustomUser
        fields = ('email', 'first_name', 'last_name', 'is_ca_firm', 'password', 'password2')
        extra_kwargs = {
            'first_name': {'required': True},
            'last_name': {'required': True},
        }

    def validate(self, data):
        """
        Check that the two passwords match.
        """
        if data['password'] != data['password2']:
            raise serializers.ValidationError({"password": "Password fields didn't match."})
        return data

    def validate_email(self, value):
        """
        Ensure email is unique (case-insensitive) and normalize to lowercase.
        Prevent creating multiple accounts with the same email but different casing.
        """
        email_lower = value.lower()
        if CustomUser.objects.filter(email__iexact=email_lower).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return email_lower

    def create(self, validated_data):
        """
        Creates and returns a new user instance, given the validated data.
        """
        # Remove confirmation password
        validated_data.pop('password2')
        
        # Create user using the manager's create_user method
        user = CustomUser.objects.create_user(
            email=validated_data['email'],
            password=validated_data['password'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
            is_ca_firm=validated_data.get('is_ca_firm', False)
        )
        return user

class CustomUserSerializer(serializers.ModelSerializer):
    """
    Read/Write serializer for retrieving and updating user profile data.
    """
    class Meta:
        model = CustomUser
        # Exclude sensitive fields like password
        fields = ('id', 'email', 'first_name', 'last_name', 'is_ca_firm', 'is_active', 'date_joined')
        read_only_fields = ('email', 'is_ca_firm', 'is_active', 'date_joined')

class GoogleLoginSerializer(serializers.Serializer):
    """
    Serializer to validate Google OAuth token.
    """
    token = serializers.CharField(required=True)

class PasswordResetRequestSerializer(serializers.Serializer):
    """
    Serializer to validate email for password reset request.
    """
    email = serializers.EmailField()

    class Meta:
        fields = ['email']

class SetNewPasswordSerializer(serializers.Serializer):
    """
    Serializer for setting a new password using reset token.
    """
    password = serializers.CharField(write_only=True, style={'input_type': 'password'})
    token = serializers.CharField(write_only=True)
    uidb64 = serializers.CharField(write_only=True)

    class Meta:
        fields = ['password', 'token', 'uidb64']

    def validate(self, attrs):
        try:
            password = attrs.get('password')
            token = attrs.get('token')
            uidb64 = attrs.get('uidb64')

            id = force_str(urlsafe_base64_decode(uidb64))
            user = CustomUser.objects.get(id=id)
            if not PasswordResetTokenGenerator().check_token(user, token):
                raise serializers.ValidationError("The reset link is invalid", 401)
            
            user.set_password(password)
            user.save()
            return user
        except Exception as e:
            raise serializers.ValidationError("The reset link is invalid", 401)
        return super().validate(attrs)