"""
Script to fix user_id in transactions that were created with wrong user_id
This updates transactions to match the correct player user_id based on who likely created them
"""
import os
from pymongo import MongoClient
from datetime import datetime

MONGO_URL = os.getenv('MONGO_URL', 'mongodb://localhost:27017/')
client = MongoClient(MONGO_URL)
db = client.chipbot

game_id = "68e4f73f5bfcaaa02570a608"

# Get all players in the game
players = list(db.players.find({"game_id": game_id}))
print(f"Found {len(players)} players:")
for p in players:
    print(f"  - {p['name']}: user_id={p['user_id']}, is_host={p.get('is_host', False)}")

# Get all transactions with wrong user_id
old_user_id = 1759834435448
transactions = list(db.transactions.find({"game_id": game_id, "user_id": old_user_id}))
print(f"\nFound {len(transactions)} transactions with old user_id {old_user_id}")

if not transactions:
    print("No transactions to fix!")
    exit(0)

# Ask which player these transactions belong to
print("\nWhich player created these transactions?")
for i, p in enumerate(players):
    print(f"{i+1}. {p['name']} (user_id: {p['user_id']})")

choice = input("Enter number: ").strip()
try:
    player_idx = int(choice) - 1
    if player_idx < 0 or player_idx >= len(players):
        print("Invalid choice!")
        exit(1)

    correct_player = players[player_idx]
    correct_user_id = correct_player['user_id']

    print(f"\nUpdating {len(transactions)} transactions from user_id {old_user_id} to {correct_user_id}")

    result = db.transactions.update_many(
        {"game_id": game_id, "user_id": old_user_id},
        {"$set": {"user_id": correct_user_id}}
    )

    print(f"Updated {result.modified_count} transactions")

    # Show updated transactions
    print("\nUpdated transactions:")
    for tx in db.transactions.find({"game_id": game_id}):
        print(f"  {tx['_id']}: type={tx['type']}, amount={tx['amount']}, user_id={tx['user_id']}")

except ValueError:
    print("Invalid input!")
    exit(1)
