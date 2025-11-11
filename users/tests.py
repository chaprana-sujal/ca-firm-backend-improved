# users/tests.py
"""
Comprehensive test suite for user authentication and management
Run with: python manage.py test users
"""

from django.test import TestCase, TransactionTestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
import json

User = get_user_model()


class UserModelTests(TestCase):
    """Test custom user model"""
    
    def setUp(self):
        self.user_data = {
            'email': 'test@example.com',
            'password': 'testpass123!@#',
            'first_name': 'Test',
            'last_name': 'User'
        }
    
    def test_create_user(self):
        """Test creating a regular user"""
        user = User.objects.create_user(**self.user_data)
        
        self.assertEqual(user.email, self.user_data['email'])
        self.assertTrue(user.check_password(self.user_data['password']))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.is_ca_firm)
        self.assertTrue(user.is_active)
    
    def test_create_superuser(self):
        """Test creating a superuser"""
        admin_user = User.objects.create_superuser(
            email='admin@example.com',
            password='adminpass123!@#'
        )
        
        self.assertTrue(admin_user.is_staff)
        self.assertTrue(admin_user.is_superuser)
        self.assertTrue(admin_user.is_active)
    
    def test_create_ca_firm_user(self):
        """Test creating a CA firm staff user"""
        ca_user = User.objects.create_user(
            email='ca@example.com',
            password='capass123!@#',
            is_ca_firm=True
        )
        
        self.assertTrue(ca_user.is_ca_firm)
        self.assertFalse(ca_user.is_staff)
    
    def test_email_normalization(self):
        """Test that emails are normalized to lowercase"""
        user = User.objects.create_user(
            email='Test@EXAMPLE.COM',
            password='testpass123!@#'
        )
        
        self.assertEqual(user.email, 'test@example.com')
    
    def test_user_string_representation(self):
        """Test the string representation of user"""
        user = User.objects.create_user(**self.user_data)
        self.assertEqual(str(user), self.user_data['email'])
    
    def test_full_name_property(self):
        """Test the full_name property"""
        user = User.objects.create_user(**self.user_data)
        expected_name = f"{self.user_data['first_name']} {self.user_data['last_name']}"
        self.assertEqual(user.full_name, expected_name)


class UserRegistrationTests(APITestCase):
    """Test user registration endpoint"""
    
    def setUp(self):
        self.client = APIClient()
        self.register_url = reverse('auth_register')
        
        self.valid_client_data = {
            'email': 'client@example.com',
            'password': 'SecurePass123!@#',
            'password2': 'SecurePass123!@#',
            'first_name': 'Client',
            'last_name': 'User',
            'is_ca_firm': False
        }
        
        self.valid_ca_data = {
            'email': 'ca@example.com',
            'password': 'SecurePass123!@#',
            'password2': 'SecurePass123!@#',
            'first_name': 'CA',
            'last_name': 'Staff',
            'is_ca_firm': True
        }
    
    def test_register_client_success(self):
        """Test successful client registration"""
        response = self.client.post(
            self.register_url,
            self.valid_client_data,
            format='json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('user', response.data)
        self.assertIn('tokens', response.data)
        self.assertEqual(response.data['user']['email'], self.valid_client_data['email'])
        self.assertFalse(response.data['user']['is_ca_firm'])
        
        # Verify user was created in database
        user = User.objects.get(email=self.valid_client_data['email'])
        self.assertTrue(user.check_password(self.valid_client_data['password']))
    
    def test_register_ca_firm_success(self):
        """Test successful CA firm staff registration"""
        response = self.client.post(
            self.register_url,
            self.valid_ca_data,
            format='json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data['user']['is_ca_firm'])
    
    def test_register_password_mismatch(self):
        """Test registration with mismatched passwords"""
        data = self.valid_client_data.copy()
        data['password2'] = 'DifferentPassword123!@#'
        
        response = self.client.post(self.register_url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password', response.data)
    
    def test_register_duplicate_email(self):
        """Test registration with existing email"""
        # Create first user
        User.objects.create_user(
            email=self.valid_client_data['email'],
            password='password123'
        )
        
        # Try to register with same email
        response = self.client.post(
            self.register_url,
            self.valid_client_data,
            format='json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_register_missing_required_fields(self):
        """Test registration with missing fields"""
        data = {
            'email': 'test@example.com',
            'password': 'testpass123'
            # Missing password2, first_name, last_name
        }
        
        response = self.client.post(self.register_url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class UserAuthenticationTests(APITestCase):
    """Test user login and JWT token functionality"""
    
    def setUp(self):
        self.client = APIClient()
        self.login_url = reverse('auth_login')
        self.refresh_url = reverse('auth_refresh')
        
        self.user_data = {
            'email': 'test@example.com',
            'password': 'testpass123!@#',
            'first_name': 'Test',
            'last_name': 'User'
        }
        
        self.user = User.objects.create_user(**self.user_data)
    
    def test_login_success(self):
        """Test successful login"""
        response = self.client.post(
            self.login_url,
            {
                'email': self.user_data['email'],
                'password': self.user_data['password']
            },
            format='json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)
    
    def test_login_wrong_password(self):
        """Test login with incorrect password"""
        response = self.client.post(
            self.login_url,
            {
                'email': self.user_data['email'],
                'password': 'wrongpassword'
            },
            format='json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_login_nonexistent_user(self):
        """Test login with non-existent email"""
        response = self.client.post(
            self.login_url,
            {
                'email': 'nonexistent@example.com',
                'password': 'password123'
            },
            format='json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_token_refresh(self):
        """Test JWT token refresh"""
        # Get initial tokens
        login_response = self.client.post(
            self.login_url,
            {
                'email': self.user_data['email'],
                'password': self.user_data['password']
            },
            format='json'
        )
        
        refresh_token = login_response.data['refresh']
        
        # Test refresh
        response = self.client.post(
            self.refresh_url,
            {'refresh': refresh_token},
            format='json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)


class UserProfileTests(APITestCase):
    """Test user profile retrieval and update"""
    
    def setUp(self):
        self.client = APIClient()
        self.profile_url = reverse('user_profile')
        
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123!@#',
            first_name='Test',
            last_name='User'
        )
        
        # Authenticate
        refresh = RefreshToken.for_user(self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
    
    def test_get_profile(self):
        """Test retrieving user profile"""
        response = self.client.get(self.profile_url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['email'], self.user.email)
        self.assertEqual(response.data['first_name'], self.user.first_name)
    
    def test_update_profile(self):
        """Test updating user profile"""
        update_data = {
            'first_name': 'Updated',
            'last_name': 'Name'
        }
        
        response = self.client.patch(
            self.profile_url,
            update_data,
            format='json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['first_name'], update_data['first_name'])
        self.assertEqual(response.data['last_name'], update_data['last_name'])
        
        # Verify in database
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, update_data['first_name'])
    
    def test_profile_unauthenticated(self):
        """Test accessing profile without authentication"""
        self.client.credentials()  # Remove authentication
        response = self.client.get(self.profile_url)
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_cannot_update_email(self):
        """Test that email cannot be updated"""
        response = self.client.patch(
            self.profile_url,
            {'email': 'newemail@example.com'},
            format='json'
        )
        
        # Email should remain unchanged
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'test@example.com')


class UserPermissionsTests(APITestCase):
    """Test role-based permissions"""
    
    def setUp(self):
        self.client = APIClient()
        
        # Create client user
        self.client_user = User.objects.create_user(
            email='client@example.com',
            password='clientpass123',
            is_ca_firm=False
        )
        
        # Create CA firm user
        self.ca_user = User.objects.create_user(
            email='ca@example.com',
            password='capass123',
            is_ca_firm=True
        )
    
    def test_client_permissions(self):
        """Test client user has correct permissions"""
        self.assertFalse(self.client_user.is_ca_firm)
        self.assertFalse(self.client_user.is_staff)
        self.assertTrue(self.client_user.is_active)
    
    def test_ca_firm_permissions(self):
        """Test CA firm user has correct permissions"""
        self.assertTrue(self.ca_user.is_ca_firm)
        self.assertFalse(self.ca_user.is_staff)  # Not Django admin staff by default
        self.assertTrue(self.ca_user.is_active)


# Run tests with: python manage.py test users
# For coverage report: coverage run --source='users' manage.py test users
# View coverage: coverage report