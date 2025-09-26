"""
Tests for all user actions in the ChipMate bot
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from telegram import Update, User, Message, Chat
from telegram.ext import ContextTypes
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.models.game import Game
from src.models.player import Player
from src.models.transaction import Transaction
from src.dal.games_dal import GamesDAL
from src.dal.players_dal import PlayersDAL
from src.dal.transactions_dal import TransactionsDAL
from datetime import datetime


class TestUserActions:
    """Test all user actions"""

    def setup_method(self):
        """Setup test environment for each test"""
        # Mock database
        self.mock_db = MagicMock()
        self.games_dal = GamesDAL(self.mock_db)
        self.players_dal = PlayersDAL(self.mock_db)
        self.transactions_dal = TransactionsDAL(self.mock_db)

        # Mock collections
        self.mock_db.games = MagicMock()
        self.mock_db.players = MagicMock()
        self.mock_db.transactions = MagicMock()

        # Mock telegram objects
        self.mock_user = User(id=12345, first_name="TestUser", is_bot=False)
        self.mock_host_user = User(id=67890, first_name="HostUser", is_bot=False)
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

        # Sample game data
        self.sample_game = Game(
            host_id=67890,
            host_name="HostUser",
            status="active",
            code="ABC12"
        )

        self.sample_player = Player(
            game_id="game123",
            user_id=12345,
            name="TestUser",
            buyins=[100],
            final_chips=150,
            is_host=False
        )

    @pytest.mark.asyncio
    async def test_start_command_new_user(self):
        """Test /start command for new user"""
        # Import here to avoid circular imports
        from main import start

        # Mock no active player
        self.mock_db.players.find_one.return_value = None

        await start(self.mock_update, self.mock_context)

        # Verify welcome message sent
        self.mock_message.reply_text.assert_called_once()
        args = self.mock_message.reply_text.call_args[0]
        assert "ChipMate" in args[0]
        assert "newgame" in args[0] or "join" in args[0]

    @pytest.mark.asyncio
    async def test_start_command_existing_player(self):
        """Test /start command for user with active game"""
        from main import start

        # Mock active player
        self.mock_db.players.find_one.return_value = {
            "game_id": "game123",
            "user_id": 12345,
            "active": True,
            "quit": False,
            "is_host": False
        }

        await start(self.mock_update, self.mock_context)

        # Verify message about existing game
        self.mock_message.reply_text.assert_called_once()
        args = self.mock_message.reply_text.call_args[0]
        assert "already in an active game" in args[0] or "current game" in args[0]

    @pytest.mark.asyncio
    async def test_newgame_success(self):
        """Test successful game creation"""
        from main import newgame

        # Mock no active player
        self.mock_db.players.find_one.return_value = None
        # Mock game creation
        self.mock_db.games.insert_one.return_value = MagicMock()
        self.mock_db.games.insert_one.return_value.inserted_id = "game123"

        await newgame(self.mock_update, self.mock_context)

        # Verify game and player created
        self.mock_db.games.insert_one.assert_called_once()
        self.mock_message.reply_text.assert_called_once()
        args = self.mock_message.reply_text.call_args[0]
        assert "created" in args[0].lower()

    @pytest.mark.asyncio
    async def test_newgame_already_in_game(self):
        """Test game creation when user already in game"""
        from main import newgame

        # Mock active player
        self.mock_db.players.find_one.return_value = {
            "game_id": "game123",
            "active": True,
            "quit": False
        }

        await newgame(self.mock_update, self.mock_context)

        # Verify error message
        self.mock_message.reply_text.assert_called_once()
        args = self.mock_message.reply_text.call_args[0]
        assert "already in" in args[0].lower()

    @pytest.mark.asyncio
    async def test_join_success(self):
        """Test successful game join"""
        from main import join_text

        # Mock join command
        self.mock_message.text = "join ABC12"

        # Mock no active player
        self.mock_db.players.find_one.return_value = None
        # Mock game exists
        self.mock_db.games.find_one.return_value = {
            "_id": "game123",
            "code": "ABC12",
            "status": "active",
            "host_id": 67890,
            "players": []
        }

        await join_text(self.mock_update, self.mock_context)

        # Verify player added
        self.mock_message.reply_text.assert_called_once()
        args = self.mock_message.reply_text.call_args[0]
        assert "joined" in args[0].lower() or "welcome" in args[0].lower()

    @pytest.mark.asyncio
    async def test_join_invalid_code(self):
        """Test join with invalid game code"""
        from main import join_text

        self.mock_message.text = "join INVALID"

        # Mock no active player
        self.mock_db.players.find_one.return_value = None
        # Mock game not found
        self.mock_db.games.find_one.return_value = None

        await join_text(self.mock_update, self.mock_context)

        # Verify error message
        self.mock_message.reply_text.assert_called_once()
        args = self.mock_message.reply_text.call_args[0]
        assert "not found" in args[0].lower() or "invalid" in args[0].lower()

    @pytest.mark.asyncio
    async def test_status_command(self):
        """Test status command"""
        from main import status

        # Mock active player
        self.mock_db.players.find_one.return_value = {
            "game_id": "game123",
            "user_id": 12345,
            "active": True,
            "quit": False,
            "is_host": False
        }

        # Mock game exists
        self.mock_db.games.find_one.return_value = {
            "_id": "game123",
            "code": "ABC12",
            "status": "active"
        }

        # Mock transactions for buyins
        self.mock_db.transactions.find.return_value = [
            {"type": "buyin_cash", "amount": 100, "confirmed": True},
            {"type": "buyin_register", "amount": 50, "confirmed": True}
        ]

        await status(self.mock_update, self.mock_context)

        # Verify status displayed
        self.mock_message.reply_text.assert_called_once()
        args = self.mock_message.reply_text.call_args[0]
        assert "ABC12" in args[0]
        assert "Cash Buy-ins" in args[0]
        assert "Credit Buy-ins" in args[0]

    @pytest.mark.asyncio
    async def test_status_no_game(self):
        """Test status when not in game"""
        from main import status

        # Mock no active player
        self.mock_db.players.find_one.return_value = None

        await status(self.mock_update, self.mock_context)

        # Verify error message
        self.mock_message.reply_text.assert_called_once()
        args = self.mock_message.reply_text.call_args[0]
        assert "not in an active game" in args[0]

    @pytest.mark.asyncio
    async def test_buyin_start(self):
        """Test buyin flow start"""
        from main import buyin_start

        # Mock active player
        self.mock_db.players.find_one.return_value = {
            "game_id": "game123",
            "user_id": 12345,
            "active": True,
            "quit": False
        }

        await buyin_start(self.mock_update, self.mock_context)

        # Verify buyin options presented
        self.mock_message.reply_text.assert_called_once()
        args = self.mock_message.reply_text.call_args[0]
        assert "buy in" in args[0].lower()

    @pytest.mark.asyncio
    async def test_cashout_start(self):
        """Test cashout flow start"""
        from main import cashout_start

        # Mock active player with chips
        self.mock_db.players.find_one.return_value = {
            "game_id": "game123",
            "user_id": 12345,
            "active": True,
            "quit": False,
            "final_chips": 150
        }

        await cashout_start(self.mock_update, self.mock_context)

        # Verify cashout prompt
        self.mock_message.reply_text.assert_called_once()
        args = self.mock_message.reply_text.call_args[0]
        assert "cashout" in args[0].lower() or "amount" in args[0].lower()

    @pytest.mark.asyncio
    async def test_chips_start(self):
        """Test chips update flow start"""
        from main import chips_start

        # Mock active player
        self.mock_db.players.find_one.return_value = {
            "game_id": "game123",
            "user_id": 12345,
            "active": True,
            "quit": False
        }

        await chips_start(self.mock_update, self.mock_context)

        # Verify chips prompt
        self.mock_message.reply_text.assert_called_once()
        args = self.mock_message.reply_text.call_args[0]
        assert "chips" in args[0].lower()

    @pytest.mark.asyncio
    async def test_quit_start(self):
        """Test quit flow start"""
        from main import quit_start

        # Mock active player
        self.mock_db.players.find_one.return_value = {
            "game_id": "game123",
            "user_id": 12345,
            "active": True,
            "quit": False,
            "is_host": False
        }

        await quit_start(self.mock_update, self.mock_context)

        # Verify quit confirmation
        self.mock_message.reply_text.assert_called_once()
        args = self.mock_message.reply_text.call_args[0]
        assert "quit" in args[0].lower() and "confirm" in args[0].lower()

    @pytest.mark.asyncio
    async def test_help_command(self):
        """Test help command"""
        from main import help_handler

        await help_handler(self.mock_update, self.mock_context)

        # Verify help message
        self.mock_message.reply_text.assert_called_once()
        args = self.mock_message.reply_text.call_args[0]
        assert "help" in args[0].lower() or "commands" in args[0].lower()

    @pytest.mark.asyncio
    async def test_mygame_command(self):
        """Test mygame command"""
        from main import mygame

        # Mock active player
        self.mock_db.players.find_one.return_value = {
            "game_id": "game123",
            "user_id": 12345,
            "active": True,
            "quit": False,
            "is_host": True
        }

        # Mock game data
        self.mock_db.games.find_one.return_value = {
            "_id": "game123",
            "code": "ABC12",
            "status": "active",
            "host_id": 12345
        }

        # Mock other players
        self.mock_db.players.find.return_value = [
            {"user_id": 12345, "name": "TestUser", "active": True, "quit": False},
            {"user_id": 99999, "name": "Player2", "active": True, "quit": False}
        ]

        await mygame(self.mock_update, self.mock_context)

        # Verify game info displayed
        self.mock_message.reply_text.assert_called_once()
        args = self.mock_message.reply_text.call_args[0]
        assert "ABC12" in args[0] or "game" in args[0].lower()


class TestHostActions:
    """Test host-specific actions"""

    def setup_method(self):
        """Setup test environment for each test"""
        # Mock database and DALs (same as above)
        self.mock_db = MagicMock()
        self.mock_db.games = MagicMock()
        self.mock_db.players = MagicMock()
        self.mock_db.transactions = MagicMock()

        # Mock telegram objects for host
        self.mock_host_user = User(id=67890, first_name="HostUser", is_bot=False)
        self.mock_chat = Chat(id=1, type="private")
        self.mock_message = MagicMock(spec=Message)
        self.mock_message.text = ""
        self.mock_message.reply_text = AsyncMock()

        self.mock_update = MagicMock(spec=Update)
        self.mock_update.effective_user = self.mock_host_user
        self.mock_update.message = self.mock_message

        self.mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        self.mock_context.user_data = {}

    @pytest.mark.asyncio
    async def test_host_buyin_start(self):
        """Test host buyin for other players"""
        from main import host_buyin_start

        # Mock host player
        self.mock_db.players.find_one.return_value = {
            "game_id": "game123",
            "user_id": 67890,
            "active": True,
            "quit": False,
            "is_host": True
        }

        # Mock other players in game
        self.mock_db.players.find.return_value = [
            {"user_id": 67890, "name": "HostUser", "active": True, "quit": False},
            {"user_id": 12345, "name": "Player1", "active": True, "quit": False}
        ]

        await host_buyin_start(self.mock_update, self.mock_context)

        # Verify player selection presented
        self.mock_message.reply_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_host_cashout_start(self):
        """Test host cashout for other players"""
        from main import host_cashout_start

        # Mock host player
        self.mock_db.players.find_one.return_value = {
            "game_id": "game123",
            "user_id": 67890,
            "active": True,
            "quit": False,
            "is_host": True
        }

        # Mock other players in game
        self.mock_db.players.find.return_value = [
            {"user_id": 67890, "name": "HostUser", "active": True, "quit": False},
            {"user_id": 12345, "name": "Player1", "active": True, "quit": False}
        ]

        await host_cashout_start(self.mock_update, self.mock_context)

        # Verify player selection presented
        self.mock_message.reply_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_host_status(self):
        """Test host status view of all players"""
        from main import host_status

        # Mock host player
        self.mock_db.players.find_one.return_value = {
            "game_id": "game123",
            "user_id": 67890,
            "active": True,
            "quit": False,
            "is_host": True
        }

        # Mock game data
        self.mock_db.games.find_one.return_value = {
            "_id": "game123",
            "code": "ABC12",
            "status": "active"
        }

        # Mock all players in game
        self.mock_db.players.find.return_value = [
            {"user_id": 67890, "name": "HostUser", "buyins": [200], "final_chips": 250, "active": True, "quit": False},
            {"user_id": 12345, "name": "Player1", "buyins": [100], "final_chips": 150, "active": True, "quit": False}
        ]

        await host_status(self.mock_update, self.mock_context)

        # Verify all players status shown
        self.mock_message.reply_text.assert_called_once()
        args = self.mock_message.reply_text.call_args[0]
        assert "Player1" in args[0] and "HostUser" in args[0]


class TestAdminActions:
    """Test admin-specific actions"""

    def setup_method(self):
        """Setup test environment for admin tests"""
        # Mock database and admin user
        self.mock_db = MagicMock()
        self.mock_db.games = MagicMock()
        self.mock_db.players = MagicMock()

        self.mock_admin_user = User(id=99999, first_name="AdminUser", is_bot=False)
        self.mock_message = MagicMock(spec=Message)
        self.mock_message.text = ""
        self.mock_message.reply_text = AsyncMock()

        self.mock_update = MagicMock(spec=Update)
        self.mock_update.effective_user = self.mock_admin_user
        self.mock_update.message = self.mock_message

        self.mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        self.mock_context.user_data = {}

        # Mock admin environment
        os.environ["ADMIN_USERS"] = "99999"

    @pytest.mark.asyncio
    async def test_admin_login_success(self):
        """Test successful admin login"""
        from main import admin_text_login

        self.mock_message.text = "admin test password"

        await admin_text_login(self.mock_update, self.mock_context)

        # Verify admin menu presented
        self.mock_message.reply_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_admin_list_games(self):
        """Test admin list all games"""
        from main import admin_list_all_games

        # Mock games in database
        self.mock_db.games.find.return_value = [
            {"_id": "game1", "code": "ABC12", "status": "active", "host_name": "Host1"},
            {"_id": "game2", "code": "XYZ99", "status": "ended", "host_name": "Host2"}
        ]

        # Set admin context
        self.mock_context.user_data["admin_authenticated"] = True

        await admin_list_all_games(self.mock_update, self.mock_context)

        # Verify games listed
        self.mock_message.reply_text.assert_called_once()
        args = self.mock_message.reply_text.call_args[0]
        assert "ABC12" in args[0] and "XYZ99" in args[0]

    def teardown_method(self):
        """Clean up admin environment"""
        if "ADMIN_USERS" in os.environ:
            del os.environ["ADMIN_USERS"]


if __name__ == "__main__":
    pytest.main([__file__])