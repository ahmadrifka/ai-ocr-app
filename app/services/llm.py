"""Call an LLM with vision to extract text, classify, and summarize an image."""

import base64
import json
from openai import AsyncOpenAI

from app.config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
from app.schemas import AnalysisResult

SYSTEM_PROMPT = """\
Analyze the uploaded receipt image and extract its transaction details.
These uploads are business expense receipts, so set transaction_type exactly to "EXPENSES".

Extract description from the receipt's purpose/note field (for example Catatan Transfer,
Catatan, or Keterangan) whenever available. Use that description to select exactly one
category from the user's expense table below. Do not invent a category or change its spelling.

Expense description → category:
- Purchase of production materials / raw ingredients → Bahan Baku
- Salary or payroll → Biaya-Gaji Karyawan
- Meals, snacks, or refreshments → Biaya-Konsumsi
- Office stationery, supplies, or administration expenses → Biaya-Perlengkapan Kantor dan Administrasi
- Business travel or office vehicle costs → Biaya-Transportasi
- Shipping, courier, or delivery service → Biaya-Ongkir
- Repairs to facilities or buildings → Biaya-Perbaikan Bangunan
- Routine operating costs (electricity, water, internet, cleaning, small daily business expenses) → Biaya-Operasional
- Purchase of equipment or assets → Biaya-Pembelian Aset
- Donations or social activities → Biaya-Sosial
- If the description does not fit any rule or is too unclear → Uncategorized

Examples:
- "Mocaf 50 kg" → Bahan Baku
- "Ongkir Affiliate" → Biaya-Ongkir
- "Ongkir Sampel dan Good Food" → Biaya-Ongkir

Return exactly these JSON fields:
- transaction_date: date and time shown for the transaction, as ISO 8601 with timezone offset (WIB is +07:00); if only a date is present, use local midnight; null if unavailable
- transaction_id: bank transfer/reference ID exactly as printed; null if unavailable
- description: concise receipt description; empty string if unavailable
- category: exactly one category listed above
- transaction_type: exactly "EXPENSES"
- beneficiary_bank, beneficiary_account_number, benecifiacry_account_name
- source_bank, source_account_number, source_account_name
- amount: numeric amount only, without currency symbols; null if unavailable. Indonesian dots are thousands separators (Rp640.000 → 640000; 73.325 → 73325).

Use null for unavailable optional fields. Never infer or invent account details. Keep account numbers as strings to preserve leading zeroes. Return only valid JSON, with no markdown fences.
"""


async def analyze_image(image_bytes: bytes, mime_type: str) -> AnalysisResult:
    """Send the image to the LLM and return structured analysis."""
    client = AsyncOpenAI(
        api_key=LLM_API_KEY,
        base_url=LLM_BASE_URL,
    )
    b64 = base64.b64encode(image_bytes).decode()

    response = await client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Analyze this image."},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{b64}"},
                    },
                ],
            },
        ],
        temperature=0.1,
        max_tokens=2000,
    )

    raw = response.choices[0].message.content or "{}"
    # Strip markdown fences if the model adds them anyway
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()

    data = json.loads(raw)
    return AnalysisResult(**data)
