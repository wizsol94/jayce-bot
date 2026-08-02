from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from decimal import Decimal, InvalidOperation

from .models import PriceQuote

logger = logging.getLogger("jace.price_alerts")


class PriceProviderError(RuntimeError):
    pass


class DexScreenerPriceProvider:
    source_name = "DexScreener"
    token_endpoint = "https://api.dexscreener.com/latest/dex/tokens/{}"

    def __init__(self, timeout_seconds: int = 8, opener=None):
        self.timeout_seconds = timeout_seconds
        self.opener = opener or urllib.request.urlopen

    def get_quotes(self, addresses: list[str]) -> dict[str, PriceQuote]:
        quotes = {}
        for address in dict.fromkeys(addresses):
            try:
                quotes[address] = self.get_quote(address)
            except PriceProviderError as exc:
                logger.warning(
                    "[price alert] quote unavailable address=%s reason=%s", address, exc
                )
            except Exception:
                logger.exception(
                    "[price alert] unexpected quote failure address=%s", address
                )
        return quotes

    def get_quote(self, address: str) -> PriceQuote:
        request = urllib.request.Request(
            self.token_endpoint.format(address),
            headers={"User-Agent": "JACE-PriceAlerts/1.0"},
        )
        try:
            with self.opener(request, timeout=self.timeout_seconds) as response:
                payload = json.load(response)
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise PriceProviderError("Price data is temporarily unavailable. Please try again shortly.") from exc
        if not isinstance(payload, dict):
            raise PriceProviderError("Price data is temporarily unavailable. Please try again shortly.")
        pairs = [pair for pair in payload.get("pairs", []) if pair.get("chainId") == "solana"]
        candidates = [pair for pair in pairs if str((pair.get("baseToken") or {}).get("address", "")).lower() == address.lower()]
        quote = self._select_pair(candidates)
        if not quote:
            raise PriceProviderError("Token not found or no valid Solana pair is available.")
        return quote

    def _select_pair(self, pairs: list[dict]) -> PriceQuote | None:
        valid = []
        for pair in pairs:
            try:
                price = Decimal(str(pair.get("priceUsd")))
                liquidity = Decimal(str((pair.get("liquidity") or {}).get("usd") or 0))
                volume = Decimal(str((pair.get("volume") or {}).get("h24") or 0))
            except (InvalidOperation, ValueError, TypeError):
                continue
            if not price.is_finite() or price <= 0 or not pair.get("pairAddress"):
                continue
            valid.append((liquidity, volume, pair))
        if not valid:
            return None
        _, _, pair = max(valid, key=lambda item: (item[0], item[1]))
        base = pair.get("baseToken") or {}
        return PriceQuote(
            address=base.get("address"),
            name=base.get("name") or "Unknown token",
            symbol=base.get("symbol") or "UNKNOWN",
            pair_address=pair["pairAddress"],
            price=Decimal(str(pair["priceUsd"])),
            liquidity_usd=Decimal(str((pair.get("liquidity") or {}).get("usd") or 0)),
            volume_24h_usd=Decimal(str((pair.get("volume") or {}).get("h24") or 0)),
            source=self.source_name,
            source_url=pair.get("url"),
        )
