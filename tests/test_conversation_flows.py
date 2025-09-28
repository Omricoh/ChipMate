"""
Tests for conversation flows and edge cases in ChipMate bot
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from telegram import Update, User, Message, Chat
from telegram.ext import ContextTypes, ConversationHandler
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestConversationFlows:
    """Test multi-step conversation flows"""

    def setup_method(self):
        """Setup test environment for each test"""
        # Mock database
        self.mock_db = MagicMock()
        self.mock_db.games = MagicMock()
        self.mock_db.players = MagicMock()
        self.mock_db.transactions = MagicMock()

        # Mock telegram objects
        self.mock_user = User(id=12345, first_name="TestUser", is_bot=False)
        self.mock_chat = Chat(id=1, type="private")
        self.mock_message = MagicMock(spec=Message)
        self.mock_message.text = ""
        self.mock_message.reply_text = AsyncMock()

        self.mock_update = MagicMock(spec=Update)
        self.mock_update.effective_user = self.mock_user
        self.mock_update.message = self.mock_message

        self.mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        self.mock_context.user_data = {}
        self.mock_context.bot = MagicMock()
        self.mock_context.bot.send_message = AsyncMock()

    @pytest.mark.asyncio
    async def test_buyin_conversation_cash(self):
        """Test complete cash buyin conversation flow"""
        from src.ui.handlers.conversation_handlers import buyin_start, buyin_type, buyin_amount

        # Mock active player
        self.mock_db.players.find_one.return_value = {
            "game_id": "game123",
            "user_id": 12345,
            "active": True,
            "quit": False
        }

        # Step 1: Start buyin
        await buyin_start(self.mock_update, self.mock_context)

        # Step 2: Choose cash
        self.mock_message.text = "💰 Cash"
        result = await buyin_type(self.mock_update, self.mock_context)
        assert self.mock_context.user_data["buy_type"] == "cash"

        # Step 3: Enter amount
        self.mock_message.text = "100"
        self.mock_db.transactions.insert_one.return_value = MagicMock()
        self.mock_db.games.find_one.return_value = {"host_id": 67890}

        await buyin_amount(self.mock_update, self.mock_context)

        # Verify transaction created
        self.mock_db.transactions.insert_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_buyin_conversation_credit(self):
        """Test complete credit buyin conversation flow"""
        from src.ui.handlers.conversation_handlers import buyin_type, buyin_amount

        # Mock active player
        self.mock_db.players.find_one.return_value = {
            "game_id": "game123",
            "user_id": 12345,
            "active": True,
            "quit": False
        }

        # Step 2: Choose credit/register
        self.mock_message.text = "💳 Register"
        result = await buyin_type(self.mock_update, self.mock_context)
        assert self.mock_context.user_data["buy_type"] == "register"

        # Step 3: Enter amount
        self.mock_message.text = "50"
        self.mock_db.transactions.insert_one.return_value = MagicMock()
        self.mock_db.games.find_one.return_value = {"host_id": 67890}

        await buyin_amount(self.mock_update, self.mock_context)

        # Verify transaction created with correct type
        args = self.mock_db.transactions.insert_one.call_args[0][0]
        assert args["type"] == "buyin_register"

    @pytest.mark.asyncio
    async def test_buyin_invalid_amount(self):
        """Test buyin with invalid amount"""
        from src.ui.handlers.conversation_handlers import buyin_amount

        # Mock active player
        self.mock_db.players.find_one.return_value = {
            "game_id": "game123",
            "user_id": 12345,
            "active": True,
            "quit": False
        }

        # Invalid amount
        self.mock_message.text = "invalid"
        self.mock_context.user_data["buy_type"] = "cash"

        result = await buyin_amount(self.mock_update, self.mock_context)

        # Should stay in conversation and ask again
        self.mock_message.reply_text.assert_called_once()
        args = self.mock_message.reply_text.call_args[0][0]
        assert "valid number" in args

    @pytest.mark.asyncio
    async def test_cashout_conversation(self):
        """Test complete cashout conversation flow"""
        from src.ui.handlers.conversation_handlers import cashout_start, cashout_amount

        # Mock active player with chips
        self.mock_db.players.find_one.return_value = {
            "game_id": "game123",
            "user_id": 12345,
            "active": True,
            "quit": False,
            "final_chips": 200
        }

        # Step 1: Start cashout
        await cashout_start(self.mock_update, self.mock_context)

        # Step 2: Enter amount
        self.mock_message.text = "150"
        self.mock_db.transactions.insert_one.return_value = MagicMock()
        self.mock_db.games.find_one.return_value = {"host_id": 67890}

        await cashout_amount(self.mock_update, self.mock_context)

        # Verify cashout transaction created
        self.mock_db.transactions.insert_one.assert_called_once()
        args = self.mock_db.transactions.insert_one.call_args[0][0]
        assert args["type"] == "cashout"

    @pytest.mark.asyncio
    async def test_cashout_invalid_amount(self):
        """Test cashout with invalid amount"""
        from src.ui.handlers.conversation_handlers import cashout_amount

        # Mock active player
        self.mock_db.players.find_one.return_value = {
            "game_id": "game123",
            "user_id": 12345,
            "active": True,
            "quit": False,
            "final_chips": 200
        }

        # Invalid amount
        self.mock_message.text = "not_a_number"

        result = await cashout_amount(self.mock_update, self.mock_context)

        # Should stay in conversation
        self.mock_message.reply_text.assert_called_once()
        args = self.mock_message.reply_text.call_args[0][0]
        assert "valid number" in args

    # Chips functionality has been removed - test removed

    @pytest.mark.asyncio
    async def test_quit_conversation(self):
        """Test quit game conversation flow"""
        from src.ui.handlers.conversation_handlers import quit_start, quit_confirm

        # Mock active player
        self.mock_db.players.find_one.return_value = {
            "game_id": "game123",
            "user_id": 12345,
            "active": True,
            "quit": False,
            "is_host": False
        }

        # Step 1: Start quit
        await quit_start(self.mock_update, self.mock_context)

        # Step 2: Confirm quit
        self.mock_message.text = "✅ Yes"

        await quit_confirm(self.mock_update, self.mock_context)

        # Verify player marked as quit
        self.mock_db.players.update_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_quit_cancel(self):
        """Test canceling quit"""
        from src.ui.handlers.conversation_handlers import quit_confirm

        # Mock active player
        self.mock_db.players.find_one.return_value = {
            "game_id": "game123",
            "user_id": 12345,
            "active": True,
            "quit": False,
            "is_host": False
        }

        # Cancel quit
        self.mock_message.text = "❌ No"

        await quit_confirm(self.mock_update, self.mock_context)

        # Verify player not updated
        self.mock_db.players.update_one.assert_not_called()

    @pytest.mark.asyncio
    async def test_host_buyin_conversation(self):
        """Test host buyin for other players conversation"""
        from src.ui.handlers.conversation_handlers import host_buyin_start, host_buyin_player, host_buyin_type, host_buyin_amount

        # Mock host player
        self.mock_db.players.find_one.return_value = {
            "game_id": "game123",
            "user_id": 67890,
            "active": True,
            "quit": False,
            "is_host": True
        }

        # Mock players in game
        self.mock_db.players.find.return_value = [
            {"user_id": 67890, "name": "HostUser", "active": True, "quit": False},
            {"user_id": 12345, "name": "Player1", "active": True, "quit": False}
        ]

        # Step 1: Start host buyin
        await host_buyin_start(self.mock_update, self.mock_context)

        # Step 2: Select player
        self.mock_message.text = "Player1"
        await host_buyin_player(self.mock_update, self.mock_context)
        assert self.mock_context.user_data["selected_player_id"] == 12345

        # Step 3: Select type
        self.mock_message.text = "💰 Cash"
        await host_buyin_type(self.mock_update, self.mock_context)
        assert self.mock_context.user_data["buy_type"] == "cash"

        # Step 4: Enter amount
        self.mock_message.text = "100"
        self.mock_db.transactions.insert_one.return_value = MagicMock()

        await host_buyin_amount(self.mock_update, self.mock_context)

        # Verify transaction created for selected player
        self.mock_db.transactions.insert_one.assert_called_once()
        args = self.mock_db.transactions.insert_one.call_args[0][0]
        assert args["user_id"] == 12345

    @pytest.mark.asyncio
    async def test_admin_login_conversation(self):
        """Test admin login conversation"""
        from src.ui.handlers.conversation_handlers import admin_text_login

        # Set admin user
        os.environ["ADMIN_USERS"] = "99999"
        self.mock_update.effective_user = User(id=99999, first_name="AdminUser", is_bot=False)

        # Admin login command
        self.mock_message.text = "admin testuser testpass"

        await admin_text_login(self.mock_update, self.mock_context)

        # Verify admin authenticated
        assert self.mock_context.user_data.get("admin_authenticated") is True

        # Cleanup
        if "ADMIN_USERS" in os.environ:
            del os.environ["ADMIN_USERS"]


class TestEdgeCases:
    """Test edge cases and error conditions"""

    def setup_method(self):
        """Setup test environment"""
        self.mock_db = MagicMock()
        self.mock_db.games = MagicMock()
        self.mock_db.players = MagicMock()
        self.mock_db.transactions = MagicMock()

        self.mock_user = User(id=12345, first_name="TestUser", is_bot=False)
        self.mock_message = MagicMock(spec=Message)
        self.mock_message.text = ""
        self.mock_message.reply_text = AsyncMock()

        self.mock_update = MagicMock(spec=Update)
        self.mock_update.effective_user = self.mock_user
        self.mock_update.message = self.mock_message

        self.mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        self.mock_context.user_data = {}

    @pytest.mark.asyncio
    async def test_action_without_active_game(self):
        """Test actions when user has no active game"""
        from main import buyin_start, cashout_start, quit_start

        # Mock no active player
        self.mock_db.players.find_one.return_value = None

        # Test each action
        actions = [buyin_start, cashout_start, quit_start]

        for action in actions:
            self.mock_message.reply_text.reset_mock()
            await action(self.mock_update, self.mock_context)

            # Should get error message
            self.mock_message.reply_text.assert_called_once()
            args = self.mock_message.reply_text.call_args[0][0]
            assert "not in an active game" in args or "no active game" in args

    @pytest.mark.asyncio
    async def test_join_already_in_game(self):
        """Test joining when already in game"""
        from main import join_text

        self.mock_message.text = "join ABC12"

        # Mock already in game
        self.mock_db.players.find_one.return_value = {
            "game_id": "existing_game",
            "active": True,
            "quit": False
        }

        await join_text(self.mock_update, self.mock_context)

        # Should get error message
        self.mock_message.reply_text.assert_called_once()
        args = self.mock_message.reply_text.call_args[0][0]
        assert "already in" in args

    @pytest.mark.asyncio
    async def test_non_host_accessing_host_functions(self):
        """Test non-host trying to use host functions"""
        from main import host_buyin_start, host_cashout_start, host_status

        # Mock regular player (not host)
        self.mock_db.players.find_one.return_value = {
            "game_id": "game123",
            "user_id": 12345,
            "active": True,
            "quit": False,
            "is_host": False
        }

        # Test host functions
        host_functions = [host_buyin_start, host_cashout_start, host_status]

        for func in host_functions:
            self.mock_message.reply_text.reset_mock()
            await func(self.mock_update, self.mock_context)

            # Should get permission error
            self.mock_message.reply_text.assert_called_once()
            args = self.mock_message.reply_text.call_args[0][0]
            assert "host" in args.lower() or "permission" in args.lower()

    @pytest.mark.asyncio
    async def test_database_connection_error(self):
        """Test handling of database connection errors"""
        from main import status

        # Mock database error
        self.mock_db.players.find_one.side_effect = Exception("Database connection failed")

        await status(self.mock_update, self.mock_context)

        # Should handle gracefully
        self.mock_message.reply_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_negative_buyin_amount(self):
        """Test negative buyin amount"""
        from main import buyin_amount

        # Mock active player
        self.mock_db.players.find_one.return_value = {
            "game_id": "game123",
            "user_id": 12345,
            "active": True,
            "quit": False
        }

        # Negative amount
        self.mock_message.text = "-50"
        self.mock_context.user_data["buy_type"] = "cash"

        await buyin_amount(self.mock_update, self.mock_context)

        # Should reject negative amount
        self.mock_message.reply_text.assert_called_once()
        args = self.mock_message.reply_text.call_args[0][0]
        assert "positive" in args or "valid" in args

    @pytest.mark.asyncio
    async def test_zero_buyin_amount(self):
        """Test zero buyin amount"""
        from main import buyin_amount

        # Mock active player
        self.mock_db.players.find_one.return_value = {
            "game_id": "game123",
            "user_id": 12345,
            "active": True,
            "quit": False
        }

        # Zero amount
        self.mock_message.text = "0"
        self.mock_context.user_data["buy_type"] = "cash"

        await buyin_amount(self.mock_update, self.mock_context)

        # Should reject zero amount
        self.mock_message.reply_text.assert_called_once()
        args = self.mock_message.reply_text.call_args[0][0]
        assert "positive" in args or "valid" in args


if __name__ == "__main__":
    pytest.main([__file__])