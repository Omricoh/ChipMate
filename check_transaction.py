"""
Quick script to check transaction type in database
"""
import os
from pymongo import MongoClient

MONGO_URL = os.getenv('MONGO_URL', 'mongodb://localhost:27017/')
client = MongoClient(MONGO_URL)
db = client.chipbot

# Find the transaction by ID from the log
tx_id = "68e4e9188810947c831b0fde"

try:
    from bson import ObjectId
    tx = db.transactions.find_one({"_id": ObjectId(tx_id)})

    if tx:
        print(f"Transaction found!")
        print(f"  Type: {tx.get('type')}")
        print(f"  Amount: {tx.get('amount')}")
        print(f"  User ID: {tx.get('user_id')}")
        print(f"  Game ID: {tx.get('game_id')}")
        print(f"  Confirmed: {tx.get('confirmed')}")
        print(f"  Rejected: {tx.get('rejected')}")
    else:
        print(f"Transaction with ID {tx_id} not found")

    # Show all transactions for debugging
    print("\nAll recent transactions:")
    recent_txs = db.transactions.find().sort('_id', -1).limit(5)
    for tx in recent_txs:
        print(f"  {tx['_id']}: type={tx.get('type')}, amount={tx.get('amount')}, confirmed={tx.get('confirmed')}, rejected={tx.get('rejected')}")

except Exception as e:
    print(f"Error: {e}")
