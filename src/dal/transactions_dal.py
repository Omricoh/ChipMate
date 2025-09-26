from bson import ObjectId
from src.models.transaction import Transaction

class TransactionsDAL:
    def __init__(self, db):
        self.col = db.transactions

    def create(self, tx: Transaction):
        res = self.col.insert_one(tx.model_dump())
        return str(res.inserted_id)

    def add_transaction(self, tx: Transaction):
        """Alias for create method to match test expectations"""
        return self.create(tx)

    def update_status(self, tx_id, confirmed: bool, rejected: bool = False):
        if isinstance(tx_id, str):
            tx_id = ObjectId(tx_id)
        self.col.update_one({"_id": tx_id}, {"$set": {"confirmed": confirmed, "rejected": rejected}})

    def get(self, tx_id):
        if isinstance(tx_id, str):
            tx_id = ObjectId(tx_id)
        return self.col.find_one({"_id": tx_id})

    def get_transaction(self, tx_id):
        """Alias for get method to match test expectations"""
        if isinstance(tx_id, str):
            tx_id = ObjectId(tx_id)
        doc = self.col.find_one({"_id": tx_id})
        if doc:
            return Transaction(**doc)
        return None

    def confirm_transaction(self, tx_id):
        """Confirm a transaction"""
        self.update_status(tx_id, True, False)

    def reject_transaction(self, tx_id):
        """Reject a transaction"""
        self.update_status(tx_id, False, True)
