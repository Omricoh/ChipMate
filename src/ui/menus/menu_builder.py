"""
Menu Builder - UI Layer
Creates Telegram keyboard menus
"""
from telegram import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton

class MenuBuilder:
    """Utility class for building Telegram menus"""

    @staticmethod
    def get_player_menu():
        """Get player menu keyboard"""
        return ReplyKeyboardMarkup([
            ["💰 Buy-in", "💸 Cashout"],
            ["🚪 Quit", "📊 Status"],
            ["❓ Help"]
        ], resize_keyboard=True)

    @staticmethod
    def get_host_menu(game_id: str = None, has_active_players: bool = True):
        """Get host menu keyboard"""
        menu_rows = [
            ["👤 Player List", "➕ Add Player"],
            ["💰 Host Buy-in", "💸 Host Cashout"],
            ["⚖️ Settle", "📈 View Settlement"],
            ["📊 Status", "📋 Game Report"],
            ["📱 Share QR", "❓ Help"]
        ]

        # Only add End Game if no active players left (all cashed out)
        if not has_active_players:
            menu_rows[0].append("🔚 End Game")

        return ReplyKeyboardMarkup(menu_rows, resize_keyboard=True)

    @staticmethod
    def get_admin_menu():
        """Get admin menu keyboard"""
        return ReplyKeyboardMarkup([
            ["📊 Manage Active Games", "📋 List All Games"],
            ["⏰ Expire Old Games", "🗑️ Delete Expired"],
            ["📈 System Stats", "❓ Admin Help"]
        ], resize_keyboard=True)

    @staticmethod
    def get_admin_game_menu():
        """Get admin game management menu"""
        return ReplyKeyboardMarkup([
            ["📊 Game Status", "📋 Game Report"],
            ["💰 Add Buy-in", "💸 Add Cashout"],
            ["🔚 End Game", "🗑️ Destroy Game"],
            ["👤 Player List", "📈 View Settlement"],
            ["🔙 Back to Games List", "❌ Exit Admin"]
        ], resize_keyboard=True)

    @staticmethod
    def get_buyin_type_menu():
        """Get buyin type selection menu"""
        return ReplyKeyboardMarkup([
            ["💵 Cash", "💳 Credit"],
            ["❌ Cancel"]
        ], resize_keyboard=True, one_time_keyboard=True)

    @staticmethod
    def get_confirmation_menu(confirm_text: str = "✅ Confirm", cancel_text: str = "❌ Cancel"):
        """Get confirmation menu"""
        return ReplyKeyboardMarkup([
            [confirm_text, cancel_text]
        ], resize_keyboard=True, one_time_keyboard=True)

    @staticmethod
    def get_transaction_approval_buttons(tx_id: str):
        """Get inline buttons for transaction approval"""
        return InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Approve", callback_data=f"approve:{tx_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject:{tx_id}")
        ]])

    @staticmethod
    def get_host_selection_buttons(players, action: str = "select"):
        """Get inline buttons for host selection"""
        buttons = []
        for player in players:
            callback_data = f"{action}:{player['user_id']}"
            button_text = f"👑 {player['name']}"
            buttons.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

        buttons.append([InlineKeyboardButton("❌ Cancel Cashout", callback_data="cancel_cashout")])
        return InlineKeyboardMarkup(buttons)

    @staticmethod
    def create_player_selection_keyboard(players, include_cancel: bool = True):
        """Create keyboard for player selection"""
        buttons = []
        for player in players:
            display_name = f"{player.name} (ID: {player.user_id})"
            buttons.append([display_name])

        if include_cancel:
            buttons.append(["❌ Cancel"])

        return ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)

    @staticmethod
    def create_game_list_keyboard(games, max_games: int = 10):
        """Create keyboard for game selection"""
        buttons = []
        for i, game in enumerate(games[:max_games]):
            game_text = f"{game.code} - {game.host_name} ({game.status})"
            buttons.append([game_text])

        buttons.append(["🔙 Back to Admin Menu"])
        return ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)