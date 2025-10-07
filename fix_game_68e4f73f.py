"""
Fix transactions for game 68e4f73f5bfcaaa02570a608
Assigns orphaned transactions to the correct players
"""
import os
from pymongo import MongoClient

MONGO_URL = os.getenv('MONGO_URL')
if not MONGO_URL:
    print("ERROR: MONGO_URL environment variable not set")
    exit(1)

client = MongoClient(MONGO_URL)
db = client.chipbot

game_id = "68e4f73f5bfcaaa02570a608"

# Get players
players = list(db.players.find({"game_id": game_id}))
print(f"Players in game:")
for p in players:
    print(f"  {p['name']}: user_id={p['user_id']}, is_host={p.get('is_host', False)}")

# Get transactions with orphaned user_id
orphaned_user_id = 1759834435448
transactions = list(db.transactions.find({"game_id": game_id, "user_id": orphaned_user_id}))
print(f"\nOrphaned transactions: {len(transactions)}")
for tx in transactions:
    print(f"  {tx['type']}: {tx['amount']} chips, confirmed={tx['confirmed']}")

if not transactions:
    print("No orphaned transactions to fix!")
    exit(0)

# Find player2 (non-host)
player2 = next((p for p in players if not p.get('is_host')), None)
if not player2:
    print("Could not find player2!")
    exit(1)

print(f"\nAssigning transactions to {player2['name']} (user_id={player2['user_id']})")

confirm = input("Continue? (y/n): ").strip().lower()
if confirm != 'y':
    print("Aborted.")
    exit(0)

# Update transactions
result = db.transactions.update_many(
    {"game_id": game_id, "user_id": orphaned_user_id},
    {"$set": {"user_id": player2['user_id']}}
)

print(f"\nUpdated {result.modified_count} transactions")
print("Done!")
