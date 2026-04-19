from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase

from accounts.validators import AdminPasswordValidator, admin_password_validator
from dice_game.normalize_slashes_middleware import NormalizeSlashesMiddleware
from game.templatetags.format_filters import indian_int


class AdminPasswordValidatorTests(SimpleTestCase):
    def test_rejects_too_short_password(self):
        validator = AdminPasswordValidator(min_length=10)
        with self.assertRaises(ValidationError) as ctx:
            validator.validate("Aa1@short")
        self.assertEqual(ctx.exception.code, "password_too_short")

    def test_rejects_password_without_uppercase(self):
        with self.assertRaises(ValidationError) as ctx:
            AdminPasswordValidator().validate("lower1@case")
        self.assertEqual(ctx.exception.code, "password_no_upper")

    def test_rejects_password_without_lowercase(self):
        with self.assertRaises(ValidationError) as ctx:
            AdminPasswordValidator().validate("UPPER1@CASE")
        self.assertEqual(ctx.exception.code, "password_no_lower")

    def test_rejects_password_without_digit(self):
        with self.assertRaises(ValidationError) as ctx:
            AdminPasswordValidator().validate("NoDigit@Here")
        self.assertEqual(ctx.exception.code, "password_no_digit")

    def test_rejects_password_without_special_character(self):
        with self.assertRaises(ValidationError) as ctx:
            AdminPasswordValidator().validate("NoSpecial1")
        self.assertEqual(ctx.exception.code, "password_no_special")

    def test_accepts_valid_password_and_has_help_text(self):
        validator = AdminPasswordValidator(min_length=8)
        self.assertIsNone(validator.validate("Strong1!"))
        self.assertIn("8", validator.get_help_text())

    def test_module_level_validator_is_initialized(self):
        self.assertIsInstance(admin_password_validator, AdminPasswordValidator)


class IndianIntFilterTests(SimpleTestCase):
    def test_none_or_invalid_values_return_zero(self):
        self.assertEqual(indian_int(None), "0")
        self.assertEqual(indian_int("abc"), "0")

    def test_short_numbers_keep_plain_format(self):
        self.assertEqual(indian_int(123), "123")
        self.assertEqual(indian_int(-99), "-99")

    def test_large_numbers_use_indian_grouping(self):
        self.assertEqual(indian_int(1234567), "12,34,567")
        self.assertEqual(indian_int(-1234567), "-12,34,567")


class NormalizeSlashesMiddlewareTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_redirects_path_with_multiple_slashes_and_keeps_query_string(self):
        middleware = NormalizeSlashesMiddleware(lambda request: HttpResponse("ok"))
        request = self.factory.get("//api//game//version/?foo=bar")
        request.path = "//api//game//version/"
        request.META["QUERY_STRING"] = "foo=bar"

        response = middleware(request)

        self.assertEqual(response.status_code, 301)
        self.assertEqual(response["Location"], "/api/game/version/?foo=bar")

    def test_passes_clean_paths_through(self):
        middleware = NormalizeSlashesMiddleware(lambda request: HttpResponse("ok"))
        request = self.factory.get("/api/game/version/")

        response = middleware(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"ok")


