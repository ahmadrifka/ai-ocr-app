import re

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas import AnalysisResult


def _normalize(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").casefold())


async def beneficiary_is_account(
    db: AsyncSession, result: AnalysisResult
) -> bool:
    """Return whether the OCR beneficiary matches one of our public.accounts rows."""
    account_number = _normalize(result.beneficiary_account_number)
    bank_name = _normalize(result.beneficiary_bank)
    account_name = _normalize(result.benecifiacry_account_name)

    if account_number:
        query = """
            SELECT EXISTS (
                SELECT 1
                FROM public.accounts
                WHERE regexp_replace(lower(account_number::text), '[^[:alnum:]]', '', 'g')
                    = :account_number
        """
        params = {"account_number": account_number}
        if bank_name:
            query += """
                AND regexp_replace(lower(bank_name::text), '[^[:alnum:]]', '', 'g')
                    = :bank_name
            """
            params["bank_name"] = bank_name
        query += ")"
    elif bank_name and account_name:
        query = """
            SELECT EXISTS (
                SELECT 1
                FROM public.accounts
                WHERE regexp_replace(lower(bank_name::text), '[^[:alnum:]]', '', 'g')
                    = :bank_name
                  AND regexp_replace(lower(account_name::text), '[^[:alnum:]]', '', 'g')
                    = :account_name
            )
        """
        params = {"bank_name": bank_name, "account_name": account_name}
    else:
        return False

    result_set = await db.execute(text(query), params)
    return bool(result_set.scalar_one())
