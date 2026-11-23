import json
import sys
import unittest
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import app.services.llm as llm
from app.schemas import AnalysisResult


class LlmProviderTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.expected = AnalysisResult(
            is_receipt=True,
            description="receipt",
            category="Uncategorized",
            transaction_type="EXPENSES",
        )
        self.openai_response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=self.expected.model_dump_json())
                )
            ]
        )
        self.openai_client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(
                    create=AsyncMock(return_value=self.openai_response)
                )
            )
        )

    def test_analysis_response_rejects_unexpected_fields(self):
        payload = json.loads(self.expected.model_dump_json())
        payload["confidence"] = 0.99

        with self.assertRaises(ValueError):
            llm._parse_analysis_response(json.dumps(payload))

    def test_analysis_response_rejects_negative_amount(self):
        payload = json.loads(self.expected.model_dump_json())
        payload["amount"] = "-1"

        with self.assertRaises(ValueError):
            llm._parse_analysis_response(json.dumps(payload))

    def test_analysis_response_requires_receipt_classification(self):
        payload = json.loads(self.expected.model_dump_json())
        del payload["is_receipt"]

        with self.assertRaises(ValueError):
            llm._parse_analysis_response(json.dumps(payload))

    def test_analysis_response_rejects_non_boolean_receipt_classification(self):
        payload = json.loads(self.expected.model_dump_json())
        payload["is_receipt"] = "false"

        with self.assertRaises(ValueError):
            llm._parse_analysis_response(json.dumps(payload))

    async def test_google_genai_provider_uses_google_adapter(self):
        google_adapter = AsyncMock(return_value=self.expected)
        with (
            patch.object(llm, "LLM_PROVIDER", "google_genai", create=True),
            patch.object(llm, "_analyze_with_google_genai", google_adapter, create=True),
            patch.object(llm, "AsyncOpenAI", return_value=self.openai_client) as openai_factory,
        ):
            result = await llm.analyze_image(b"receipt-image", "image/jpeg")

        self.assertEqual(result, self.expected)
        google_adapter.assert_awaited_once_with(b"receipt-image", "image/jpeg")
        openai_factory.assert_not_called()

    async def test_openai_provider_remains_available(self):
        with (
            patch.object(llm, "LLM_PROVIDER", "openai"),
            patch.object(llm, "AsyncOpenAI", return_value=self.openai_client) as openai_factory,
        ):
            result = await llm.analyze_image(b"receipt-image", "image/jpeg")

        self.assertEqual(result, self.expected)
        openai_factory.assert_called_once_with(
            api_key=llm.LLM_API_KEY,
            base_url=llm.LLM_BASE_URL,
        )
        self.openai_client.chat.completions.create.assert_awaited_once()

    async def test_google_sdk_receives_image_and_returns_structured_result(self):
        response = SimpleNamespace(
            text=self.expected.model_dump_json(), usage_metadata=None
        )
        generate_content = AsyncMock(return_value=response)
        async_client = SimpleNamespace(
            models=SimpleNamespace(generate_content=generate_content),
            aclose=AsyncMock(),
        )
        google_client = SimpleNamespace(aio=async_client, close=Mock())

        google_module = ModuleType("google")
        google_module.__path__ = []
        genai_module = ModuleType("google.genai")
        genai_client_factory = Mock(return_value=google_client)
        setattr(genai_module, "Client", genai_client_factory)
        types_module = ModuleType("google.genai.types")
        part_from_bytes = Mock(return_value="image-part")
        setattr(types_module, "Part", SimpleNamespace(from_bytes=part_from_bytes))
        config_value = object()
        config_factory = Mock(return_value=config_value)
        setattr(types_module, "GenerateContentConfig", config_factory)
        setattr(google_module, "genai", genai_module)
        setattr(genai_module, "types", types_module)

        with (
            patch.dict(
                sys.modules,
                {
                    "google": google_module,
                    "google.genai": genai_module,
                    "google.genai.types": types_module,
                },
            ),
            patch.object(llm, "LLM_PROVIDER", "google_genai", create=True),
            patch.object(llm, "AsyncOpenAI", return_value=self.openai_client) as openai_factory,
        ):
            result = await llm.analyze_image(b"receipt-image", "image/jpeg")

        self.assertEqual(result, self.expected)
        genai_client_factory.assert_called_once_with(api_key=llm.LLM_API_KEY)
        part_from_bytes.assert_called_once_with(data=b"receipt-image", mime_type="image/jpeg")
        config_factory.assert_called_once_with(
            system_instruction=llm.SYSTEM_PROMPT,
            response_mime_type="application/json",
            max_output_tokens=2000,
        )
        generate_content.assert_awaited_once_with(
            model=llm.LLM_MODEL,
            contents=["Analyze this image.", "image-part"],
            config=config_value,
        )
        async_client.aclose.assert_awaited_once()
        google_client.close.assert_called_once()
        openai_factory.assert_not_called()
