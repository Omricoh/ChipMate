"""
Diagnostic script to check game state
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

print("=" * 60)
print("GAME DIAGNOSTICS")
print("=" * 60)

# Check game
game = db.games.find_one({"_id": game_id})
if game:
    print(f"\nGame: {game.get('code')}")
    print(f"  Status: {game.get('status')}")
    print(f"  Host: {game.get('host_name')}")
else:
    print(f"\nGame {game_id} not found!")
    exit(1)

# Check players
players = list(db.players.find({"game_id": game_id}))
print(f"\nPlayers ({len(players)}):")
for p in players:
    print(f"  - {p['name']} (user_id={p['user_id']}, is_host={p.get('is_host', False)}, active={p.get('active', False)})")

# Check transactions
all_txs = list(db.transactions.find({"game_id": game_id}))
print(f"\nAll Transactions ({len(all_txs)}):")
for tx in all_txs:
    player = next((p for p in players if p['user_id'] == tx['user_id']), None)
    player_name = player['name'] if player else f"ORPHANED (user_id={tx['user_id']})"
    print(f"  - {player_name}: {tx['type']} {tx['amount']} (confirmed={tx.get('confirmed')}, rejected={tx.get('rejected')})")

# Check pending transactions
pending_txs = list(db.transactions.find({"game_id": game_id, "confirmed": False, "rejected": False}))
print(f"\nPending Transactions ({len(pending_txs)}):")
for tx in pending_txs:
    player = next((p for p in players if p['user_id'] == tx['user_id']), None)
    player_name = player['name'] if player else f"ORPHANED (user_id={tx['user_id']})"
    print(f"  - {player_name}: {tx['type']} {tx['amount']}")

# Check debts
debts = list(db.debts.find({"game_id": game_id}))
print(f"\nDebts ({len(debts)}):")
for debt in debts:
    print(f"  - {debt['debtor_name']} owes {debt['amount']} to {debt.get('creditor_name', 'unassigned')} (status={debt['status']})")

print("\n" + "=" * 60)

# Recommendations
if len(pending_txs) == 0:
    print("✓ No pending transactions")
else:
    orphaned = [tx for tx in pending_txs if not any(p['user_id'] == tx['user_id'] for p in players)]
    if orphaned:
        print(f"⚠ {len(orphaned)} orphaned pending transactions (user_id doesn't match any player)")
        print("  Run: python fix_game_68e4f73f.py")

confirmed_txs = [tx for tx in all_txs if tx.get('confirmed')]
if len(confirmed_txs) == 0:
    print("ℹ No confirmed transactions - players need to buy in")
else:
    orphaned = [tx for tx in confirmed_txs if not any(p['user_id'] == tx['user_id'] for p in players)]
    if orphaned:
        print(f"⚠ {len(orphaned)} orphaned confirmed transactions")
        print("  Run: python fix_game_68e4f73f.py OR python clear_test_data.py")
