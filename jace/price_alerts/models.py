from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


@dataclass(frozen=True)
class PriceQuote:
    address: str
    name: str
    symbol: str
    pair_address: str
    price: Decimal
    liquidity_usd: Decimal
    volume_24h_usd: Decimal
    source: str = "DexScreener"
    source_url: Optional[str] = None


@dataclass
class PriceAlert:
    id: int
    creator_user_id: str
    source_chat_id: str
    destination_chat_id: str
    contract_address: str
    token_name: str
    token_symbol: str
    pair_address: str
    price_source: str
    current_price: Decimal
    target_price: Decimal
    direction: str
    previous_checked_price: Optional[Decimal]
    last_checked_price: Optional[Decimal]
    created_at: str
    last_successful_check_at: Optional[str]
    triggered_at: Optional[str]
    status: str
    error_status: Optional[str]
    trigger_message_id: Optional[str]
    created_command_text: str

