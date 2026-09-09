"""Banca — un conto letto come sensore. Nessun verbo che muove denaro."""

from connectors.bank.provider import (
    AccountSummary,
    BankAPIError,
    BankProviderProtocol,
    BankRateLimited,
    FakeBankProvider,
    build_bank_provider,
)
from connectors.bank.service import (
    CAPABILITY_ID,
    CONNECTOR_ID,
    BankReadService,
    accounts_of,
)

__all__ = [
    "AccountSummary",
    "BankAPIError",
    "BankProviderProtocol",
    "BankRateLimited",
    "BankReadService",
    "CAPABILITY_ID",
    "CONNECTOR_ID",
    "FakeBankProvider",
    "accounts_of",
    "build_bank_provider",
]
