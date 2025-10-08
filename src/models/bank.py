from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import Optional


class Bank(BaseModel):
    """
    Bank entity for tracking all cash and debt flows in a game.

    HOW IT WORKS:
    1. Player brings CASH → Bank takes cash and issues CHIPS
    2. Player wants CREDIT → Bank issues CHIPS and records DEBT
    3. Player returns CHIPS → Bank pays cash or reduces debt
    4. HOST MUST APPROVE all transactions (buy-ins and cashouts)

    CRITICAL RULES:
    - Money ONLY enters bank when chips are issued (buy-in)
    - Money ONLY leaves bank when chips are returned (cashout)
    - NO money movement without host approval
    - Bank balance can NEVER go negative
    """
    game_id: str

    # Cash tracking
    cash_balance: int = 0  # Current cash in bank (cash in - cash out)
    total_cash_in: int = 0  # Total cash buy-ins received
    total_cash_out: int = 0  # Total cash paid out in cashouts

    # Credit tracking (credits are tracked per-player in Player.credits_owed)
    total_credits_issued: int = 0  # Total credits issued to all players
    total_credits_repaid: int = 0  # Total credits paid back to bank

    # Chips tracking
    total_chips_issued: int = 0  # Total chips given to players (cash + credit)
    total_chips_returned: int = 0  # Total chips returned via cashouts
    chips_in_play: int = 0  # Current chips with players

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

    def can_pay_cash(self, amount: int) -> bool:
        """Check if bank has enough cash to pay out"""
        return self.cash_balance >= amount

    def validate_cashout(self, chips_returned: int, cash_requested: int, credits_to_repay: int) -> tuple[bool, str]:
        """
        Validate a cashout request before processing.

        Rules:
        - Chips must be returned to get money back
        - Cash paid cannot exceed bank balance
        - Credits repaid tracked but no limit (player can overpay)
        """
        if chips_returned <= 0:
            return False, "Cannot cashout without returning chips"

        if cash_requested > self.cash_balance:
            return False, f"Bank only has {self.cash_balance} cash available, cannot pay {cash_requested}"

        return True, "Cashout valid"

    def record_cash_buyin(self, amount: int) -> None:
        """
        Record a cash buy-in transaction.
        REQUIRES: Host approval (enforced by transaction service)
        Player gives CASH → Bank takes cash → Bank issues CHIPS
        """
        if amount <= 0:
            raise ValueError("Buy-in amount must be positive")

        self.cash_balance += amount
        self.total_cash_in += amount
        self.total_chips_issued += amount
        self.chips_in_play += amount
        self.updated_at = datetime.now(timezone.utc)

    def record_credit_buyin(self, amount: int) -> None:
        """
        Record a credit buy-in transaction.
        REQUIRES: Host approval (enforced by transaction service)
        Bank issues CHIPS on credit → Player owes credit (tracked in Player.credits_owed)
        """
        if amount <= 0:
            raise ValueError("Buy-in amount must be positive")

        self.total_credits_issued += amount
        self.total_chips_issued += amount
        self.chips_in_play += amount
        self.updated_at = datetime.now(timezone.utc)

    def record_cashout(self, chips_returned: int, cash_paid: int, credits_repaid: int) -> None:
        """
        Record a cashout transaction.
        REQUIRES: Host approval (enforced by transaction service)
        Player returns CHIPS → Bank receives chips back
                            → Player may repay credits
                            → Bank may pay CASH

        CRITICAL: This method assumes validation has already passed.
        Use validate_cashout() first!
        """
        if chips_returned <= 0:
            raise ValueError("Must return chips to cashout")

        if cash_paid > self.cash_balance:
            raise ValueError(f"Cannot pay {cash_paid} cash, bank only has {self.cash_balance}")

        self.total_chips_returned += chips_returned
        self.chips_in_play -= chips_returned

        if cash_paid > 0:
            self.cash_balance -= cash_paid
            self.total_cash_out += cash_paid

        if credits_repaid > 0:
            self.total_credits_repaid += credits_repaid

        self.updated_at = datetime.now(timezone.utc)

    def get_available_cash(self) -> int:
        """Get available cash for cashouts"""
        return self.cash_balance

    def get_summary(self) -> dict:
        """Get bank summary for display"""
        outstanding_credits = self.total_credits_issued - self.total_credits_repaid
        return {
            'cash_balance': self.cash_balance,
            'available_cash': self.get_available_cash(),
            'outstanding_credits': outstanding_credits,
            'chips_in_play': self.chips_in_play,
            'total_cash_in': self.total_cash_in,
            'total_cash_out': self.total_cash_out,
            'total_credits_issued': self.total_credits_issued,
            'total_credits_repaid': self.total_credits_repaid
        }
