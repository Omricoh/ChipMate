"""
Data Access Layer for UnpaidCreditClaim
"""
from typing import List, Optional
from pymongo.database import Database
from src.models.unpaid_credit_claim import UnpaidCreditClaim


class UnpaidCreditClaimsDAL:
    """Data Access Layer for unpaid credit claims"""

    def __init__(self, db: Database):
        self.db = db
        self.col = db.unpaid_credit_claims

    def create(self, claim: UnpaidCreditClaim) -> str:
        """Create a new unpaid credit claim"""
        result = self.col.insert_one(claim.dict())
        return str(result.inserted_id)

    def get_by_debtor(self, game_id: str, debtor_user_id: int) -> List[UnpaidCreditClaim]:
        """Get all claims against a specific debtor"""
        claims = list(self.col.find({
            'game_id': game_id,
            'debtor_user_id': debtor_user_id
        }))
        return [UnpaidCreditClaim(**claim) for claim in claims]

    def get_by_claimant(self, game_id: str, claimant_user_id: int) -> List[UnpaidCreditClaim]:
        """Get all claims made by a specific claimant"""
        claims = list(self.col.find({
            'game_id': game_id,
            'claimant_user_id': claimant_user_id
        }))
        return [UnpaidCreditClaim(**claim) for claim in claims]

    def get_by_game(self, game_id: str) -> List[UnpaidCreditClaim]:
        """Get all claims for a game"""
        claims = list(self.col.find({'game_id': game_id}))
        return [UnpaidCreditClaim(**claim) for claim in claims]
