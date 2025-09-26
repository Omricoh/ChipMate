# Data Isolation in ChipMate

## Database Structure

### Players Collection
Each document represents a player in a specific game:

```json
{
  "_id": ObjectId,
  "game_id": "string",      // Links to specific game
  "user_id": 123456789,     // Telegram user ID
  "name": "John",
  "buyins": [100, 200],     // Buy-ins for THIS game only
  "final_chips": 450,       // Final chips in THIS game only
  "quit": false,
  "is_host": false,
  "active": true
}
```

**Key Points:**
- Composite unique key: `game_id` + `user_id`
- A user can have multiple player records (one per game they've played)
- Buy-ins and chips are specific to each game
- Only one ACTIVE player record per user at a time

### Games Collection
```json
{
  "_id": ObjectId,
  "host_id": 123456789,
  "host_name": "John",
  "status": "active",
  "created_at": ISODate,
  "players": [123456789, 987654321],  // User IDs in this game
  "code": "ABC12"
}
```

### Transactions Collection
```json
{
  "_id": ObjectId,
  "game_id": "string",      // Links to specific game
  "user_id": 123456789,
  "type": "buyin_cash",
  "amount": 100,
  "confirmed": true,
  "rejected": false,
  "at": ISODate
}
```

## Data Isolation Rules

1. **One Active Game Per User**: Users can only be in one active game at a time
2. **Game-Specific Data**: All chips, buy-ins, and transactions are tied to a specific game_id
3. **Historical Data**: When a game ends, the data remains but marked as inactive
4. **No Cross-Game Data**: Data from one game never affects another game

## Example Scenarios

### User plays multiple games (sequentially):
1. User creates Game A (code: ABC12)
   - Player record: {game_id: "gameA_id", user_id: 123, buyins: [100], chips: 150}
2. User quits Game A
   - Player record marked: {active: false, quit: true}
3. User creates Game B (code: XYZ99)
   - NEW Player record: {game_id: "gameB_id", user_id: 123, buyins: [200], chips: 180}
4. Each game has completely separate data

### Validation Checks:
- `/newgame` - Checks if user has active player record
- `/join` - Checks if user has active player record
- Buy-ins/Cashouts - Only affect current game's data
- Settlement - Only calculates for specific game's players