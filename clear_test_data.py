"""
Script to clear all test data from the database
WARNING: This will delete ALL games, players, transactions, and debts
"""
import os
from pymongo import MongoClient

MONGO_URL = os.getenv('MONGO_URL')
if not MONGO_URL:
    print("ERROR: MONGO_URL environment variable not set")
    print("Usage: MONGO_URL='your_mongo_url' python clear_test_data.py")
    exit(1)

client = MongoClient(MONGO_URL)
db = client.chipbot

print("WARNING: This will delete ALL data from the database!")
print("Collections to be cleared:")
print("  - games")
print("  - players")
print("  - transactions")
print("  - debts")
print()

confirm = input("Type 'DELETE ALL' to confirm: ").strip()
if confirm != "DELETE ALL":
    print("Aborted.")
    exit(0)

# Delete all data
games_result = db.games.delete_many({})
players_result = db.players.delete_many({})
transactions_result = db.transactions.delete_many({})
debts_result = db.debts.delete_many({})

print(f"\nDeleted:")
print(f"  - {games_result.deleted_count} games")
print(f"  - {players_result.deleted_count} players")
print(f"  - {transactions_result.deleted_count} transactions")
print(f"  - {debts_result.deleted_count} debts")
print("\nDatabase cleared successfully!")
