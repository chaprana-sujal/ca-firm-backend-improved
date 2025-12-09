from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from services.models import Document, Case, ServicePlan, Service, ServiceCategory
from users.models import CustomUser

class FileUploadSecurityTest(TestCase):
    def setUp(self):
        # Create required related objects
        self.user = CustomUser.objects.create_user(email='test@example.com', password='password')
        self.category = ServiceCategory.objects.create(name='Test Category')
        self.service = Service.objects.create(name='Test Service', category=self.category)
        self.plan = ServicePlan.objects.create(service=self.service, name='Test Plan', price=100)
        self.case = Case.objects.create(client=self.user, service_plan=self.plan)

    def test_valid_file_upload(self):
        """Test that PDF files are allowed"""
        pdf_file = SimpleUploadedFile("test.pdf", b"file_content", content_type="application/pdf")
        doc = Document(
            case=self.case,
            file=pdf_file,
            document_type="Test Doc",
            uploaded_by=self.user
        )
        try:
            doc.full_clean() # This runs validators
            doc.save()
        except ValidationError:
            self.fail("Valid PDF file raised ValidationError")

    def test_invalid_file_upload(self):
        """Test that EXE files are rejected"""
        exe_file = SimpleUploadedFile("test.exe", b"file_content", content_type="application/x-msdownload")
        doc = Document(
            case=self.case,
            file=exe_file,
            document_type="Test Doc",
            uploaded_by=self.user
        )
        with self.assertRaises(ValidationError):
            doc.full_clean() # Should raise ValidationError
