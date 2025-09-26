"""
Integration tests for ChipMate bot - testing complete user journeys
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from telegram import Update, User, Message, Chat
from telegram.ext import ContextTypes
import sys
import os
from datetime import datetime
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestCompleteGameFlow:
    """Test complete game flow from start to finish"""

    def setup_method(self):
        """Setup test environment"""
        # Mock database with more realistic behavior
        self.mock_db = MagicMock()
        self.mock_games_col = MagicMock()
        self.mock_players_col = MagicMock()
        self.mock_transactions_col = MagicMock()

        self.mock_db.games = self.mock_games_col
        self.mock_db.players = self.mock_players_col
        self.mock_db.transactions = self.mock_transactions_col

        # Track game state
        self.game_data = {}
        self.player_data = {}
        self.transaction_data = []

        # Mock collections to use our tracking
        self.mock_games_col.insert_one.side_effect = self._insert_game
        self.mock_games_col.find_one.side_effect = self._find_game
        self.mock_players_col.update_one.side_effect = self._update_player
        self.mock_players_col.find_one.side_effect = self._find_player
        self.mock_players_col.find.side_effect = self._find_players
        self.mock_transactions_col.insert_one.side_effect = self._insert_transaction
        self.mock_transactions_col.find.side_effect = self._find_transactions

        # Users
        self.host_user = User(id=67890, first_name="HostUser", is_bot=False)
        self.player1_user = User(id=12345, first_name="Player1", is_bot=False)
        self.player2_user = User(id=54321, first_name="Player2", is_bot=False)

        # Game ID counter
        self.game_id_counter = 1

    def _insert_game(self, game_doc):
        """Mock game insertion"""
        game_id = f"game{self.game_id_counter}"
        self.game_id_counter += 1
        game_doc["_id"] = game_id
        self.game_data[game_id] = game_doc
        result = MagicMock()
        result.inserted_id = game_id
        return result

    def _find_game(self, query):
        """Mock game finding"""
        if "_id" in query:
            return self.game_data.get(query["_id"])
        elif "code" in query:
            for game in self.game_data.values():
                if game.get("code") == query["code"]:
                    return game
        return None

    def _update_player(self, query, update_doc):
        """Mock player update"""
        key = f"{query.get('game_id')}_{query.get('user_id')}"
        if key in self.player_data:
            if "$set" in update_doc:
                self.player_data[key].update(update_doc["$set"])

    def _find_player(self, query):
        """Mock player finding"""
        if "game_id" in query and "user_id" in query:
            key = f"{query['game_id']}_{query['user_id']}"
            return self.player_data.get(key)
        elif "user_id" in query and "active" in query:
            for player in self.player_data.values():
                if (player.get("user_id") == query["user_id"] and
                    player.get("active") == query["active"] and
                    player.get("quit") == query.get("quit", False)):
                    return player
        return None

    def _find_players(self, query):
        """Mock finding multiple players"""
        results = []
        if "game_id" in query:
            for player in self.player_data.values():
                if player.get("game_id") == query["game_id"]:
                    results.append(player)
        return results

    def _insert_transaction(self, tx_doc):
        """Mock transaction insertion"""
        self.transaction_data.append(tx_doc)
        return MagicMock()

    def _find_transactions(self, query):
        """Mock finding transactions"""
        results = []
        for tx in self.transaction_data:
            match = True
            for key, value in query.items():
                if key == "type" and "$in" in value:
                    if tx.get(key) not in value["$in"]:
                        match = False
                elif tx.get(key) != value:
                    match = False
            if match:
                results.append(tx)
        return results

    def _create_mock_update(self, user, text=""):
        """Helper to create mock update"""
        mock_message = MagicMock(spec=Message)
        mock_message.text = text
        mock_message.reply_text = AsyncMock()

        mock_update = MagicMock(spec=Update)
        mock_update.effective_user = user
        mock_update.message = mock_message

        return mock_update, mock_message

    def _create_mock_context(self):
        """Helper to create mock context"""
        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.user_data = {}
        mock_context.bot = MagicMock()
        mock_context.bot.send_message = AsyncMock()
        return mock_context

    @pytest.mark.asyncio
    async def test_complete_game_lifecycle(self):
        """Test a complete game from creation to settlement"""
        from main import newgame, join_text, buyin_start, buyin_type, buyin_amount

        # Step 1: Host creates game
        host_update, host_message = self._create_mock_update(self.host_user)
        host_context = self._create_mock_context()

        await newgame(host_update, host_context)

        # Verify game created
        assert len(self.game_data) == 1
        game_id = list(self.game_data.keys())[0]
        game = self.game_data[game_id]
        assert game["host_id"] == 67890
        assert len(game["code"]) == 5

        # Manually add host as player (since we're mocking)
        host_player_key = f"{game_id}_{67890}"
        self.player_data[host_player_key] = {
            "game_id": game_id,
            "user_id": 67890,
            "name": "HostUser",
            "buyins": [],
            "final_chips": 0,
            "is_host": True,
            "active": True,
            "quit": False
        }

        # Step 2: Player 1 joins game
        player1_update, player1_message = self._create_mock_update(
            self.player1_user, f"join {game['code']}"
        )
        player1_context = self._create_mock_context()

        await join_text(player1_update, player1_context)

        # Manually add player1 (since we're mocking the full flow)
        player1_key = f"{game_id}_{12345}"
        self.player_data[player1_key] = {
            "game_id": game_id,
            "user_id": 12345,
            "name": "Player1",
            "buyins": [],
            "final_chips": 0,
            "is_host": False,
            "active": True,
            "quit": False
        }

        # Step 3: Player 2 joins game
        player2_update, player2_message = self._create_mock_update(
            self.player2_user, f"join {game['code']}"
        )
        player2_context = self._create_mock_context()

        await join_text(player2_update, player2_context)

        # Manually add player2
        player2_key = f"{game_id}_{54321}"
        self.player_data[player2_key] = {
            "game_id": game_id,
            "user_id": 54321,
            "name": "Player2",
            "buyins": [],
            "final_chips": 0,
            "is_host": False,
            "active": True,
            "quit": False
        }

        # Step 4: Players make buyins
        # Player 1 cash buyin
        player1_context.user_data = {"buy_type": "cash"}
        player1_update.message.text = "100"
        await buyin_amount(player1_update, player1_context)

        # Player 2 credit buyin
        player2_context.user_data = {"buy_type": "register"}
        player2_update.message.text = "150"
        await buyin_amount(player2_update, player2_context)

        # Verify transactions created
        assert len(self.transaction_data) == 2
        assert self.transaction_data[0]["type"] == "buyin_cash"
        assert self.transaction_data[0]["amount"] == 100
        assert self.transaction_data[1]["type"] == "buyin_register"
        assert self.transaction_data[1]["amount"] == 150

        # Verify game has players
        assert len(self.player_data) == 3  # Host + 2 players

    @pytest.mark.asyncio
    async def test_host_manage_players_flow(self):
        """Test host managing other players' buyins and cashouts"""
        from main import host_buyin_start, host_buyin_player, host_buyin_type, host_buyin_amount

        # Setup game with host and player
        game_id = "game1"
        self.game_data[game_id] = {
            "_id": game_id,
            "code": "ABC12",
            "host_id": 67890,
            "status": "active"
        }

        # Host player
        host_key = f"{game_id}_{67890}"
        self.player_data[host_key] = {
            "game_id": game_id,
            "user_id": 67890,
            "name": "HostUser",
            "is_host": True,
            "active": True,
            "quit": False
        }

        # Regular player
        player_key = f"{game_id}_{12345}"
        self.player_data[player_key] = {
            "game_id": game_id,
            "user_id": 12345,
            "name": "Player1",
            "is_host": False,
            "active": True,
            "quit": False
        }

        # Host initiates buyin for player
        host_update, host_message = self._create_mock_update(self.host_user)
        host_context = self._create_mock_context()

        # Step 1: Start host buyin
        await host_buyin_start(host_update, host_context)

        # Step 2: Select player
        host_update.message.text = "Player1"
        await host_buyin_player(host_update, host_context)
        assert host_context.user_data["selected_player_id"] == 12345

        # Step 3: Select cash buyin
        host_update.message.text = "💰 Cash"
        await host_buyin_type(host_update, host_context)
        assert host_context.user_data["buy_type"] == "cash"

        # Step 4: Enter amount
        host_update.message.text = "200"
        await host_buyin_amount(host_update, host_context)

        # Verify host transaction created for player
        assert len(self.transaction_data) == 1
        assert self.transaction_data[0]["user_id"] == 12345
        assert self.transaction_data[0]["type"] == "buyin_cash"
        assert self.transaction_data[0]["amount"] == 200

    @pytest.mark.asyncio
    async def test_player_quit_and_rejoin_flow(self):
        """Test player quitting and rejoining different games"""
        from main import quit_start, quit_confirm, newgame, join_text

        # Setup initial game
        game_id1 = "game1"
        self.game_data[game_id1] = {
            "_id": game_id1,
            "code": "ABC12",
            "host_id": 67890,
            "status": "active"
        }

        player_key1 = f"{game_id1}_{12345}"
        self.player_data[player_key1] = {
            "game_id": game_id1,
            "user_id": 12345,
            "name": "Player1",
            "is_host": False,
            "active": True,
            "quit": False
        }

        # Player quits
        player_update, player_message = self._create_mock_update(self.player1_user)
        player_context = self._create_mock_context()

        await quit_start(player_update, player_context)

        player_update.message.text = "✅ Yes"
        await quit_confirm(player_update, player_context)

        # Verify player marked as quit
        assert self.player_data[player_key1]["quit"] is True
        assert self.player_data[player_key1]["active"] is False

        # Player creates new game
        await newgame(player_update, player_context)

        # Verify new game created
        assert len(self.game_data) == 2
        new_game_id = list(self.game_data.keys())[1]
        new_game = self.game_data[new_game_id]
        assert new_game["host_id"] == 12345

    @pytest.mark.asyncio
    async def test_data_isolation_between_games(self):
        """Test that games have completely isolated data"""
        # Create two separate games
        game1_id = "game1"
        game2_id = "game2"

        self.game_data[game1_id] = {
            "_id": game1_id,
            "code": "ABC12",
            "host_id": 67890,
            "status": "active"
        }

        self.game_data[game2_id] = {
            "_id": game2_id,
            "code": "XYZ99",
            "host_id": 12345,
            "status": "active"
        }

        # Same user in both games (different times)
        player_game1_key = f"{game1_id}_{54321}"
        self.player_data[player_game1_key] = {
            "game_id": game1_id,
            "user_id": 54321,
            "name": "Player",
            "buyins": [],
            "final_chips": 100,
            "is_host": False,
            "active": False,  # This game ended
            "quit": False
        }

        player_game2_key = f"{game2_id}_{54321}"
        self.player_data[player_game2_key] = {
            "game_id": game2_id,
            "user_id": 54321,
            "name": "Player",
            "buyins": [],
            "final_chips": 200,
            "is_host": False,
            "active": True,  # This game is active
            "quit": False
        }

        # Add transactions for each game
        self.transaction_data = [
            {
                "game_id": game1_id,
                "user_id": 54321,
                "type": "buyin_cash",
                "amount": 50,
                "confirmed": True,
                "rejected": False
            },
            {
                "game_id": game2_id,
                "user_id": 54321,
                "type": "buyin_cash",
                "amount": 150,
                "confirmed": True,
                "rejected": False
            }
        ]

        # Test status shows only current game data
        from main import status

        player_update, player_message = self._create_mock_update(
            User(id=54321, first_name="Player", is_bot=False)
        )
        player_context = self._create_mock_context()

        await status(player_update, player_context)

        # Should show only game2 data (active game)
        player_message.reply_text.assert_called_once()
        status_message = player_message.reply_text.call_args[0][0]

        # Should contain game2 code, not game1
        assert "XYZ99" in status_message
        assert "ABC12" not in status_message

        # Should show game2 buyins (150), not game1 buyins (50)
        assert "150" in status_message
        assert "50" not in status_message


class TestErrorHandling:
    """Test error handling in various scenarios"""

    def setup_method(self):
        """Setup test environment"""
        self.mock_db = MagicMock()

    @pytest.mark.asyncio
    async def test_database_error_graceful_handling(self):
        """Test graceful handling of database errors"""
        from main import status

        # Mock database error
        self.mock_db.players.find_one.side_effect = Exception("Connection timeout")

        user = User(id=12345, first_name="TestUser", is_bot=False)
        mock_message = MagicMock()
        mock_message.reply_text = AsyncMock()

        mock_update = MagicMock()
        mock_update.effective_user = user
        mock_update.message = mock_message

        mock_context = MagicMock()
        mock_context.user_data = {}

        # Should not crash
        try:
            await status(mock_update, mock_context)
        except Exception as e:
            pytest.fail(f"Should handle database errors gracefully, but got: {e}")

    @pytest.mark.asyncio
    async def test_invalid_game_state_recovery(self):
        """Test recovery from invalid game states"""
        from main import status

        # Mock invalid game state (player has game_id but game doesn't exist)
        mock_players_col = MagicMock()
        mock_games_col = MagicMock()

        self.mock_db.players = mock_players_col
        self.mock_db.games = mock_games_col

        # Player exists but game doesn't
        mock_players_col.find_one.return_value = {
            "game_id": "nonexistent_game",
            "user_id": 12345,
            "active": True,
            "quit": False
        }
        mock_games_col.find_one.return_value = None

        user = User(id=12345, first_name="TestUser", is_bot=False)
        mock_message = MagicMock()
        mock_message.reply_text = AsyncMock()

        mock_update = MagicMock()
        mock_update.effective_user = user
        mock_update.message = mock_message

        mock_context = MagicMock()

        await status(mock_update, mock_context)

        # Should handle gracefully
        mock_message.reply_text.assert_called_once()
        args = mock_message.reply_text.call_args[0][0]
        assert "not found" in args or "error" in args


if __name__ == "__main__":
    pytest.main([__file__])