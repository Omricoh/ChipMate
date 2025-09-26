#!/usr/bin/env python
"""
Database cleanup script - removes any games without required fields
Run this once to clean up any legacy data
"""

import os
from pymongo import MongoClient

# Get MongoDB connection
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
client = MongoClient(MONGO_URL)
db = client["chipbot"]

def cleanup_games():
    """Remove games without required 'code' field"""
    # Find games without code field
    invalid_games = db.games.find({"code": {"$exists": False}})
    count = 0

    for game in invalid_games:
        game_id = game["_id"]

        # Delete related players
        db.players.delete_many({"game_id": str(game_id)})

        # Delete related transactions
        db.transactions.delete_many({"game_id": str(game_id)})

        # Delete the game
        db.games.delete_one({"_id": game_id})

        count += 1
        print(f"Deleted game {game_id} and related data")

    print(f"\nCleanup complete. Removed {count} invalid games.")

    # Show remaining games
    remaining = db.games.count_documents({})
    print(f"Remaining games in database: {remaining}")

if __name__ == "__main__":
    print("Starting database cleanup...")
    print("This will remove any games without required fields.")

    response = input("\nContinue? (yes/no): ")
    if response.lower() == "yes":
        cleanup_games()
    else:
        print("Cleanup cancelled.")