import pytest
from datetime import datetime
from src.models.transaction import Transaction

def test_transaction_buyin_cash():
    tx = Transaction(game_id="game1", user_id=5, type="buyin_cash", amount=100)
    assert tx.type == "buyin_cash"
    assert tx.amount == 100
    assert tx.confirmed is False
    assert tx.rejected is False
    assert isinstance(tx.at, datetime)

def test_transaction_cashout():
    tx = Transaction(game_id="game1", user_id=7, type="cashout", amount=250)
    assert tx.type == "cashout"
    assert tx.amount == 250
