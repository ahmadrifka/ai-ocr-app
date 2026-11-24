import unittest
from unittest.mock import patch

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.main import app
from app.services import auth


PASSWORD = "team-password"
API_KEY = "machine-key"
SESSION_SECRET = "session-secret"


def auth_settings(**overrides):
    """Patch auth settings for one test; unspecified settings are disabled."""
    values = {
        "DASHBOARD_PASSWORD": "",
        "API_KEY": "",
        "SESSION_SECRET": "",
        "APP_ENV": "development",
    } | overrides
    return patch.multiple(auth, **values)


class AuthenticatedApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async def override_db():
            async with sessions() as session:
                yield session

        previous_overrides = app.dependency_overrides.copy()
        app.dependency_overrides[get_db] = override_db
        self.addCleanup(lambda: setattr(app, "dependency_overrides", previous_overrides))

        settings = auth_settings(
            DASHBOARD_PASSWORD=PASSWORD, API_KEY=API_KEY, SESSION_SECRET=SESSION_SECRET
        )
        settings.start()
        self.addCleanup(settings.stop)

        self.client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        self.addAsyncCleanup(self.client.aclose)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_api_rejects_anonymous_requests(self):
        response = await self.client.get("/api/documents/")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"detail": "Authentication required"})

    async def test_openapi_docs_are_protected(self):
        response = await self.client.get("/openapi.json")

        self.assertEqual(response.status_code, 401)

    async def test_health_and_dashboard_files_stay_public(self):
        self.assertEqual((await self.client.get("/health")).status_code, 200)
        self.assertEqual((await self.client.get("/dashboard/login.html")).status_code, 200)

    async def test_api_key_header_grants_access(self):
        response = await self.client.get("/api/documents/", headers={"X-API-Key": API_KEY})

        self.assertEqual(response.status_code, 200)

    async def test_wrong_api_key_is_rejected(self):
        response = await self.client.get("/api/documents/", headers={"X-API-Key": "guess"})

        self.assertEqual(response.status_code, 401)

    async def test_wrong_password_does_not_create_a_session(self):
        response = await self.client.post("/auth/login", json={"password": "guess"})

        self.assertEqual(response.status_code, 401)
        self.assertNotIn(auth.SESSION_COOKIE, response.cookies)

    async def test_login_session_grants_access_until_logout(self):
        login = await self.client.post("/auth/login", json={"password": PASSWORD})
        self.assertEqual(login.status_code, 204)
        self.assertIn("httponly", login.headers["set-cookie"].lower())

        self.assertEqual((await self.client.get("/api/documents/")).status_code, 200)

        await self.client.post("/auth/logout")
        self.assertEqual((await self.client.get("/api/documents/")).status_code, 401)


class AuthDisabledTests(unittest.IsolatedAsyncioTestCase):
    async def test_api_is_open_when_no_credentials_are_configured(self):
        with auth_settings():
            self.assertFalse(auth.requires_auth("/api/documents/"))


class SessionTokenTests(unittest.TestCase):
    def setUp(self):
        settings = auth_settings(DASHBOARD_PASSWORD=PASSWORD, SESSION_SECRET=SESSION_SECRET)
        settings.start()
        self.addCleanup(settings.stop)

    def test_fresh_token_is_valid(self):
        token = auth.create_session_token(60, now=1_000)

        self.assertTrue(auth.is_valid_session(token, now=1_030))

    def test_expired_token_is_rejected(self):
        token = auth.create_session_token(60, now=1_000)

        self.assertFalse(auth.is_valid_session(token, now=1_061))

    def test_tampered_expiry_is_rejected(self):
        _, _, signature = auth.create_session_token(60, now=1_000).partition(".")

        self.assertFalse(auth.is_valid_session(f"9999999999.{signature}", now=1_030))

    def test_token_signed_with_another_secret_is_rejected(self):
        token = auth.create_session_token(60, now=1_000)

        with patch.object(auth, "SESSION_SECRET", "rotated-secret"):
            self.assertFalse(auth.is_valid_session(token, now=1_030))

    def test_malformed_tokens_are_rejected(self):
        for token in (None, "", "not-a-token", "abc.def"):
            with self.subTest(token=token):
                self.assertFalse(auth.is_valid_session(token))


class AuthConfigValidationTests(unittest.TestCase):
    def test_production_without_credentials_refuses_to_start(self):
        with auth_settings(APP_ENV="production"), self.assertRaises(RuntimeError):
            auth.validate_auth_config()

    def test_password_without_session_secret_refuses_to_start(self):
        with auth_settings(DASHBOARD_PASSWORD=PASSWORD), self.assertRaises(RuntimeError):
            auth.validate_auth_config()

    def test_production_with_credentials_is_accepted(self):
        with auth_settings(
            APP_ENV="production",
            DASHBOARD_PASSWORD=PASSWORD,
            SESSION_SECRET=SESSION_SECRET,
        ):
            auth.validate_auth_config()


if __name__ == "__main__":
    unittest.main()
