# services/tests.py
"""
Comprehensive test suite for services app
Run with: python manage.py test services
"""

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from decimal import Decimal
from django.test import override_settings

from .models import ServiceCategory, Service, ServicePlan, Case, Document, Payment

User = get_user_model()


class ServiceModelTests(TestCase):
    """Test service-related models"""
    
    def setUp(self):
        self.category = ServiceCategory.objects.create(
            name='Startup Services',
            description='Services for new businesses'
        )
        
        self.service = Service.objects.create(
            category=self.category,
            name='Proprietorship Registration',
            description='Register your proprietorship',
            is_active=True
        )
        
        self.plan = ServicePlan.objects.create(
            service=self.service,
            name='Basic',
            price=Decimal('5000.00'),
            features='Basic registration services',
            is_recommended=False
        )
    
    def test_service_category_creation(self):
        """Test creating a service category"""
        self.assertEqual(self.category.name, 'Startup Services')
        self.assertEqual(str(self.category), 'Startup Services')
    
    def test_service_creation(self):
        """Test creating a service"""
        self.assertEqual(self.service.name, 'Proprietorship Registration')
        self.assertTrue(self.service.is_active)
        self.assertEqual(str(self.service), 'Startup Services - Proprietorship Registration')
    
    def test_service_plan_creation(self):
        """Test creating a service plan"""
        self.assertEqual(self.plan.name, 'Basic')
        self.assertEqual(self.plan.price, Decimal('5000.00'))
        self.assertFalse(self.plan.is_recommended)
    
    def test_service_plans_relationship(self):
        """Test service-plan relationship"""
        plans = self.service.plans.all()
        self.assertEqual(plans.count(), 1)
        self.assertEqual(plans.first(), self.plan)


class CaseModelTests(TestCase):
    """Test case model and workflows"""
    
    def setUp(self):
        # Create users
        self.client_user = User.objects.create_user(
            email='client@example.com',
            password='clientpass123',
            is_ca_firm=False
        )
        
        self.staff_user = User.objects.create_user(
            email='staff@example.com',
            password='staffpass123',
            is_ca_firm=True
        )
        
        # Create service structure
        self.category = ServiceCategory.objects.create(name='Test Category')
        self.service = Service.objects.create(
            category=self.category,
            name='Test Service',
            description='Test description'
        )
        self.plan = ServicePlan.objects.create(
            service=self.service,
            name='Basic',
            price=Decimal('10000.00'),
            features='Test features'
        )
        
        # Create case
        self.case = Case.objects.create(
            client=self.client_user,
            service_plan=self.plan,
            status=Case.CaseStatus.PENDING
        )
    
    def test_case_creation(self):
        """Test creating a case"""
        self.assertEqual(self.case.client, self.client_user)
        self.assertEqual(self.case.service_plan, self.plan)
        self.assertEqual(self.case.status, Case.CaseStatus.PENDING)
        self.assertIsNone(self.case.assigned_staff)
    
    def test_case_status_choices(self):
        """Test all case status options"""
        status_choices = [choice[0] for choice in Case.CaseStatus.choices]
        
        expected_statuses = ['PENDING', 'PAID', 'IN_PROGRESS', 'NEEDS_DOCUMENTS', 'COMPLETED', 'CANCELED']
        
        for status in expected_statuses:
            self.assertIn(status, status_choices)
    
    def test_case_staff_assignment(self):
        """Test assigning staff to a case"""
        self.case.assigned_staff = self.staff_user
        self.case.save()
        
        self.assertEqual(self.case.assigned_staff, self.staff_user)
    
    def test_case_string_representation(self):
        """Test case __str__ method"""
        case_str = str(self.case)
        self.assertIn(str(self.case.id), case_str)
        self.assertIn(self.client_user.email, case_str)


class PaymentModelTests(TestCase):
    """Test payment model"""
    
    def setUp(self):
        self.client_user = User.objects.create_user(
            email='client@example.com',
            password='clientpass123'
        )
        
        category = ServiceCategory.objects.create(name='Test')
        service = Service.objects.create(category=category, name='Test Service')
        self.plan = ServicePlan.objects.create(
            service=service,
            name='Basic',
            price=Decimal('15000.00')
        )
        
        self.case = Case.objects.create(
            client=self.client_user,
            service_plan=self.plan
        )
    
    def test_payment_creation(self):
        """Test creating a payment"""
        payment = Payment.objects.create(
            case=self.case,
            amount=self.plan.price,
            transaction_id='TEST_TXN_123',
            is_successful=True
        )
        
        self.assertEqual(payment.case, self.case)
        self.assertEqual(payment.amount, self.plan.price)
        self.assertTrue(payment.is_successful)
    
    def test_one_payment_per_case(self):
        """Test that each case can have only one payment"""
        Payment.objects.create(
            case=self.case,
            amount=self.plan.price,
            transaction_id='TXN_1',
            is_successful=True
        )
        
        # Try to create another payment for same case (should raise error)
        with self.assertRaises(Exception):
            Payment.objects.create(
                case=self.case,
                amount=self.plan.price,
                transaction_id='TXN_2',
                is_successful=True
            )


class ServiceAPITests(APITestCase):
    """Test service listing and retrieval endpoints"""
    
    def setUp(self):
        self.client = APIClient()
        
        # Create authenticated user
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
        
        # Authenticate
        refresh = RefreshToken.for_user(self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
        
        # Create test data
        self.category = ServiceCategory.objects.create(
            name='Startup',
            description='Startup services'
        )
        
        self.service = Service.objects.create(
            category=self.category,
            name='Proprietorship',
            description='Proprietorship registration',
            is_active=True
        )
        
        self.plan = ServicePlan.objects.create(
            service=self.service,
            name='Basic',
            price=Decimal('5000.00'),
            features='Basic plan features'
        )
    
    def test_list_service_categories(self):
        """Test listing service categories"""
        url = reverse('servicecategory-list')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['name'], 'Startup')
    
    def test_retrieve_service_category(self):
        """Test retrieving a specific category"""
        url = reverse('servicecategory-detail', args=[self.category.id])
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], self.category.name)
    
    def test_list_services(self):
        """Test listing services (CA firm only)"""
        # Make user CA firm staff
        self.user.is_ca_firm = True
        self.user.save()
        
        url = reverse('service-list')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class CaseAPITests(APITestCase):
    """Test case management endpoints"""
    
    def setUp(self):
        self.client = APIClient()
        
        # Create client user
        self.client_user = User.objects.create_user(
            email='client@example.com',
            password='clientpass123',
            is_ca_firm=False
        )
        
        # Create CA firm user
        self.staff_user = User.objects.create_user(
            email='staff@example.com',
            password='staffpass123',
            is_ca_firm=True
        )
        
        # Create service structure
        category = ServiceCategory.objects.create(name='Test')
        service = Service.objects.create(category=category, name='Test Service')
        self.plan = ServicePlan.objects.create(
            service=service,
            name='Basic',
            price=Decimal('10000.00'),
            features='Features'
        )
        
        # Authenticate as client
        refresh = RefreshToken.for_user(self.client_user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
    
    def test_create_case(self):
        """Test client creating a new case"""
        url = reverse('case-list')
        data = {'service_plan': self.plan.id}
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['service_plan']['id'], self.plan.id)
        self.assertEqual(response.data['status'], Case.CaseStatus.PENDING)
    
    def test_list_client_cases(self):
        """Test client listing their own cases"""
        # Create a case
        Case.objects.create(
            client=self.client_user,
            service_plan=self.plan
        )
        
        url = reverse('case-list')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
    
    def test_client_cannot_see_other_cases(self):
        """Test client can only see their own cases"""
        # Create another user and their case
        other_user = User.objects.create_user(
            email='other@example.com',
            password='pass123'
        )
        Case.objects.create(client=other_user, service_plan=self.plan)
        
        url = reverse('case-list')
        response = self.client.get(url)
        
        # Should return 0 cases for current client
        self.assertEqual(len(response.data), 0)
    
    def test_staff_can_see_all_cases(self):
        """Test CA firm staff can see all cases"""
        # Create cases for different clients
        Case.objects.create(client=self.client_user, service_plan=self.plan)
        
        other_user = User.objects.create_user(email='other@example.com', password='pass')
        Case.objects.create(client=other_user, service_plan=self.plan)
        
        # Authenticate as staff
        refresh = RefreshToken.for_user(self.staff_user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
        
        url = reverse('case-list')
        response = self.client.get(url)
        
        # Staff should see all cases
        self.assertEqual(len(response.data), 2)


class PaymentAPITests(APITestCase):
    """Test payment processing endpoints"""
    
    def setUp(self):
        self.client = APIClient()
        
        self.client_user = User.objects.create_user(
            email='client@example.com',
            password='clientpass123'
        )
        
        category = ServiceCategory.objects.create(name='Test')
        service = Service.objects.create(category=category, name='Test Service')
        plan = ServicePlan.objects.create(
            service=service,
            name='Basic',
            price=Decimal('10000.00')
        )
        
        self.case = Case.objects.create(
            client=self.client_user,
            service_plan=plan,
            status=Case.CaseStatus.PENDING
        )
        
        # Authenticate
        refresh = RefreshToken.for_user(self.client_user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
    
    def test_process_payment(self):
        """Test processing payment for a case"""
        url = reverse('case_pay', args=[self.case.id])
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data['is_successful'])
        
        # Verify case status updated
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, Case.CaseStatus.PAID)
    
    def test_cannot_pay_twice(self):
        """Test cannot process payment twice for same case"""
        url = reverse('case_pay', args=[self.case.id])
        
        # First payment
        self.client.post(url)
        
        # Try second payment
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @override_settings(DEBUG=True)
    def test_create_razorpay_order_in_test_mode(self):
        """When DEBUG=True and no keys, creating a Razorpay order returns test payload"""
        url = reverse('razorpay_create_order', args=[self.case.id])
        response = self.client.post(url, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('test_mode', response.data)
        self.assertTrue(response.data.get('test_mode'))

        # Check payment record created with transaction_id matching returned order_id
        order_id = response.data.get('order_id')
        payment = Payment.objects.get(case=self.case)
        self.assertEqual(payment.transaction_id, order_id)
        self.assertFalse(payment.is_successful)

    @override_settings(DEBUG=True)
    def test_verify_razorpay_payment_in_test_mode(self):
        """In DEBUG test mode, verification with 'test' flag marks payment successful"""
        # Create fake order first
        create_url = reverse('razorpay_create_order', args=[self.case.id])
        create_resp = self.client.post(create_url, format='json')
        self.assertEqual(create_resp.status_code, status.HTTP_200_OK)
        order_id = create_resp.data.get('order_id')

        verify_url = reverse('razorpay_verify_payment', args=[self.case.id])
        payload = {
            'razorpay_payment_id': 'TEST_PAY_123',
            'razorpay_order_id': order_id,
            'razorpay_signature': 'IGNORED',
            'test': True
        }

        resp = self.client.post(verify_url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data.get('is_successful'))

        # Verify Payment and Case status
        payment = Payment.objects.get(case=self.case)
        self.assertTrue(payment.is_successful)
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, Case.CaseStatus.PAID)


class DocumentAPITests(APITestCase):
    """Test document upload and management"""
    
    def setUp(self):
        self.client = APIClient()
        
        self.client_user = User.objects.create_user(
            email='client@example.com',
            password='clientpass123'
        )
        
        category = ServiceCategory.objects.create(name='Test')
        service = Service.objects.create(category=category, name='Test Service')
        plan = ServicePlan.objects.create(service=service, name='Basic', price=Decimal('5000'))
        
        self.case = Case.objects.create(
            client=self.client_user,
            service_plan=plan
        )
        
        # Authenticate
        refresh = RefreshToken.for_user(self.client_user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
    
    def test_upload_document(self):
        """Test uploading a document"""
        url = reverse('document_upload', args=[self.case.id])
        
        # Create a test file
        test_file = SimpleUploadedFile(
            "test_document.pdf",
            b"file_content",
            content_type="application/pdf"
        )
        
        data = {
            'file': test_file,
            'document_type': 'Aadhaar Card',
            'case': self.case.id
        }
        
        response = self.client.post(url, data, format='multipart')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['document_type'], 'Aadhaar Card')


# Run tests with: python manage.py test services
# For coverage: coverage run --source='services' manage.py test services