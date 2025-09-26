from src.models.transaction import Transaction

class TransactionDAL:
    def __init__(self, db):
        self.col = db.transactions

    def create(self, tx: Transaction):
        return self.col.insert_one(tx.model_dump())

    def update_status(self, tx_id, confirmed: bool, rejected: bool = False):
        self.col.update_one({"_id": tx_id}, {"$set": {"confirmed": confirmed, "rejected": rejected}})

    def get(self, tx_id):
        return self.col.find_one({"_id": tx_id})
