"""In-memory account ledger for USDC and ENTROPY balances."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from threading import Lock

from src.amm.service import MarketSide, ZERO, to_decimal


@dataclass(slots=True)
class Account:
    """User account tracked inside the mock TEE ledger."""

    account_id: str
    usdc_balance: Decimal
    entropy_balance: Decimal
    staked_entropy: Decimal
    total_entropy_spent: Decimal
    query_count: int
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class Position:
    """Per-account position in a specific market."""

    account_id: str
    market_id: str
    yes_shares: Decimal
    no_shares: Decimal
    created_at: datetime
    updated_at: datetime


class InMemoryAccountService:
    """Maintain internal account balances for the demo backend."""

    def __init__(self) -> None:
        self._accounts: dict[str, Account] = {}
        self._positions: dict[tuple[str, str], Position] = {}
        self._lock = Lock()

    def get_or_create_account(self, account_id: str) -> Account:
        """Return an existing account or create a new empty one."""

        with self._lock:
            return self._get_or_create_unlocked(account_id)

    def get_account(self, account_id: str) -> Account:
        """Return an account or raise if it does not exist."""

        with self._lock:
            account = self._accounts.get(account_id)
            if account is None:
                raise KeyError(f"account '{account_id}' not found")
            return account

    def deposit_usdc(self, account_id: str, amount) -> Account:
        """Increase the internal USDC balance."""

        return self._deposit(account_id, amount, asset="usdc")

    def deposit_entropy(self, account_id: str, amount) -> Account:
        """Increase the internal ENTROPY balance."""

        return self._deposit(account_id, amount, asset="entropy")

    def debit_entropy(self, account_id: str, amount) -> Account:
        """Deduct ENTROPY from the internal account ledger."""

        debit_amount = self._require_positive(amount, "amount")
        with self._lock:
            account = self._get_or_create_unlocked(account_id)
            if account.entropy_balance < debit_amount:
                raise ValueError("insufficient ENTROPY balance")
            account.entropy_balance -= debit_amount
            account.total_entropy_spent += debit_amount
            account.query_count += 1
            account.updated_at = datetime.now(timezone.utc)
            return account

    def debit_usdc(self, account_id: str, amount) -> Account:
        """Deduct USDC from the internal account ledger."""

        debit_amount = self._require_positive(amount, "amount")
        with self._lock:
            account = self._get_or_create_unlocked(account_id)
            if account.usdc_balance < debit_amount:
                raise ValueError("insufficient USDC balance")
            account.usdc_balance -= debit_amount
            account.updated_at = datetime.now(timezone.utc)
            return account

    def withdraw_entropy(self, account_id: str, amount) -> Account:
        """Deduct ENTROPY for an external withdrawal intent."""

        debit_amount = self._require_positive(amount, "amount")
        with self._lock:
            account = self._get_or_create_unlocked(account_id)
            if account.entropy_balance < debit_amount:
                raise ValueError("insufficient ENTROPY balance")
            account.entropy_balance -= debit_amount
            account.updated_at = datetime.now(timezone.utc)
            return account

    def stake_entropy(self, account_id: str, amount) -> Account:
        """Move ENTROPY from free balance into the staked bucket."""

        stake_amount = self._require_positive(amount, "amount")
        with self._lock:
            account = self._get_or_create_unlocked(account_id)
            if account.entropy_balance < stake_amount:
                raise ValueError("insufficient ENTROPY balance")
            account.entropy_balance -= stake_amount
            account.staked_entropy += stake_amount
            account.updated_at = datetime.now(timezone.utc)
            return account

    def unstake_entropy(self, account_id: str, amount) -> Account:
        """Move ENTROPY from the staked bucket back to free balance."""

        unstake_amount = self._require_positive(amount, "amount")
        with self._lock:
            account = self._get_or_create_unlocked(account_id)
            if account.staked_entropy < unstake_amount:
                raise ValueError("insufficient staked ENTROPY balance")
            account.staked_entropy -= unstake_amount
            account.entropy_balance += unstake_amount
            account.updated_at = datetime.now(timezone.utc)
            return account

    def slash_staked_entropy(self, account_id: str, amount) -> Account:
        """Slash ENTROPY from the staked bucket."""

        slash_amount = self._require_positive(amount, "amount")
        with self._lock:
            account = self._get_or_create_unlocked(account_id)
            if account.staked_entropy < slash_amount:
                raise ValueError("insufficient staked ENTROPY balance")
            account.staked_entropy -= slash_amount
            account.updated_at = datetime.now(timezone.utc)
            return account

    def credit_usdc(self, account_id: str, amount) -> Account:
        """Credit USDC to the internal account ledger."""

        return self._deposit(account_id, amount, asset="usdc")

    def get_position(self, account_id: str, market_id: str) -> Position:
        """Return the stored position or an empty default position."""

        with self._lock:
            return self._get_or_create_position_unlocked(account_id, market_id)

    def list_accounts(self) -> list[Account]:
        """Return all accounts."""

        with self._lock:
            return list(self._accounts.values())

    def list_positions(self) -> list[Position]:
        """Return all positions."""

        with self._lock:
            return list(self._positions.values())

    def apply_buy(self, account_id: str, market_id: str, side: MarketSide, share_amount, usdc_cost) -> tuple[Account, Position]:
        """Deduct USDC and increase the market position."""

        share_delta = self._require_positive(share_amount, "share_amount")
        cost = self._require_positive(usdc_cost, "usdc_cost")
        with self._lock:
            account = self._get_or_create_unlocked(account_id)
            if account.usdc_balance < cost:
                raise ValueError("insufficient USDC balance")
            account.usdc_balance -= cost
            account.updated_at = datetime.now(timezone.utc)
            position = self._get_or_create_position_unlocked(account_id, market_id)
            if side == MarketSide.YES:
                position.yes_shares += share_delta
            else:
                position.no_shares += share_delta
            position.updated_at = datetime.now(timezone.utc)
            return account, position

    def apply_sell(self, account_id: str, market_id: str, side: MarketSide, share_amount, usdc_credit) -> tuple[Account, Position]:
        """Decrease the market position and credit USDC."""

        share_delta = self._require_positive(share_amount, "share_amount")
        credit = self._require_positive(usdc_credit, "usdc_credit")
        with self._lock:
            account = self._get_or_create_unlocked(account_id)
            position = self._get_or_create_position_unlocked(account_id, market_id)
            if side == MarketSide.YES:
                if position.yes_shares < share_delta:
                    raise ValueError("insufficient YES position")
                position.yes_shares -= share_delta
            else:
                if position.no_shares < share_delta:
                    raise ValueError("insufficient NO position")
                position.no_shares -= share_delta
            account.usdc_balance += credit
            now = datetime.now(timezone.utc)
            account.updated_at = now
            position.updated_at = now
            return account, position

    def settle_position(self, account_id: str, market_id: str, winning_side: MarketSide) -> tuple[Account, Position, Decimal]:
        """Settle a resolved market position and credit the winning payout."""

        with self._lock:
            account = self._get_or_create_unlocked(account_id)
            position = self._get_or_create_position_unlocked(account_id, market_id)
            payout = position.yes_shares if winning_side == MarketSide.YES else position.no_shares
            position.yes_shares = ZERO
            position.no_shares = ZERO
            now = datetime.now(timezone.utc)
            account.usdc_balance += payout
            account.updated_at = now
            position.updated_at = now
            return account, position, payout

    def _deposit(self, account_id: str, amount, asset: str) -> Account:
        deposit_amount = self._require_positive(amount, "amount")
        with self._lock:
            account = self._get_or_create_unlocked(account_id)
            if asset == "usdc":
                account.usdc_balance += deposit_amount
            else:
                account.entropy_balance += deposit_amount
            account.updated_at = datetime.now(timezone.utc)
            return account

    def _get_or_create_unlocked(self, account_id: str) -> Account:
        account = self._accounts.get(account_id)
        if account is None:
            now = datetime.now(timezone.utc)
            account = Account(
                account_id=account_id,
                usdc_balance=ZERO,
                entropy_balance=ZERO,
                staked_entropy=ZERO,
                total_entropy_spent=ZERO,
                query_count=0,
                created_at=now,
                updated_at=now,
            )
            self._accounts[account_id] = account
        return account

    def _get_or_create_position_unlocked(self, account_id: str, market_id: str) -> Position:
        position_key = (account_id, market_id)
        position = self._positions.get(position_key)
        if position is None:
            now = datetime.now(timezone.utc)
            position = Position(
                account_id=account_id,
                market_id=market_id,
                yes_shares=ZERO,
                no_shares=ZERO,
                created_at=now,
                updated_at=now,
            )
            self._positions[position_key] = position
        return position

    def _require_positive(self, value, field_name: str) -> Decimal:
        decimal_value = to_decimal(value)
        if decimal_value <= ZERO:
            raise ValueError(f"{field_name} must be positive")
        return decimal_value
