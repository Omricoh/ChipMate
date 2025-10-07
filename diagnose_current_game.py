"""
Diagnose the current game state to understand the cashout issue
"""
import os
from pymongo import MongoClient

MONGO_URL = os.getenv('MONGO_URL', 'mongodb://localhost:27017/')
client = MongoClient(MONGO_URL)
db = client.chipbot

# Get the most recent game
game = db.games.find_one(sort=[("_id", -1)])
if not game:
    print("No games found")
    exit(0)

game_id = str(game["_id"])
print(f"Checking game: {game_id} (code: {game.get('code')})")
print("="*60)

# Check players
players = list(db.players.find({"game_id": game_id}))
print(f"\nPlayers:")
for p in players:
    print(f"  {p['name']}: active={p.get('active')}, cashed_out={p.get('cashed_out')}, "
          f"is_host={p.get('is_host')}, final_chips={p.get('final_chips', 'N/A')}")

# Check debts
debts = list(db.debts.find({"game_id": game_id}))
print(f"\nDebts:")
for d in debts:
    creditor = d.get('creditor_name', 'Unassigned')
    print(f"  {d['debtor_name']} owes {d['amount']} to {creditor} (status: {d['status']})")

# Check cashout transactions
cashouts = list(db.transactions.find({
    "game_id": game_id,
    "type": "cashout",
    "confirmed": True
}))
print(f"\nCashout Transactions:")
for tx in cashouts:
    player = next((p for p in players if p['user_id'] == tx['user_id']), None)
    player_name = player['name'] if player else f"Unknown (user_id={tx['user_id']})"

    debt_proc = tx.get('debt_processing', {})
    debt_paid = debt_proc.get('player_debt_settlement', 0)
    cash_received = debt_proc.get('final_cash_amount', 0)
    debt_transfers = debt_proc.get('debt_transfers', [])

    print(f"\n  {player_name} cashed out {tx['amount']} chips:")
    print(f"    - Debt paid: {debt_paid}")
    print(f"    - Cash received: {cash_received}")
    print(f"    - Debt transfers: {len(debt_transfers)}")
    if debt_transfers:
        for dt in debt_transfers:
            print(f"      • {dt.get('debtor_name')} owes {dt.get('amount')}")
