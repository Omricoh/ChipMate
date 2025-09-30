"""
Message Formatter - UI Layer
Formats messages for Telegram display
"""
from typing import List, Dict, Any
from datetime import datetime, timedelta

class MessageFormatter:
    """Formats various types of messages for Telegram display"""

    def format_game_creation_message(self, game_code: str, host_name: str, join_url: str = None) -> str:
        """Format game creation message with QR code"""
        msg = (
            f"🎮 <b>Game Created Successfully!</b>\n\n"
            f"🔑 <b>Game Code:</b> <code>{game_code}</code>\n"
            f"👑 <b>Host:</b> {host_name}\n\n"
            f"📱 <b>Ways to Join:</b>\n"
            f"1. Scan this QR code\n"
            f"2. Use command: <code>/join {game_code}</code>\n"
        )

        if join_url:
            msg += f"3. Use link below\n\n"
        else:
            msg += "\n"

        msg += f"🎯 Share this QR code with players to join instantly!"
        return msg

    def format_qr_share_message(self, game, host_name: str, active_count: int, join_url: str = None) -> str:
        """Format QR code sharing message"""
        msg = (
            f"📱 <b>Share this QR Code to invite players!</b>\n\n"
            f"🎮 <b>Game:</b> <code>{game.code}</code>\n"
            f"👑 <b>Host:</b> {host_name}\n"
            f"👥 <b>Players:</b> {active_count} active\n"
            f"📅 <b>Status:</b> {game.status}\n\n"
            f"<b>How to join:</b>\n"
            f"1. 📱 Scan this QR code\n"
            f"2. 💬 Send: <code>/join {game.code}</code>\n"
        )

        if join_url:
            msg += f"3. 🔗 Use link below\n\n"
        else:
            msg += "\n"

        msg += f"🎯 Forward this message to invite others!"
        return msg

    def format_player_status(self, game, summary: Dict[str, Any], active_player: dict) -> str:
        """Format player status message"""
        msg = f"📊 **Your Status**\n\n"
        msg += f"🎮 Game: **{game.code}**\n"
        msg += f"👑 Host: {game.host_name}\n\n"

        if summary["cash_buyins"] > 0 or summary["credit_buyins"] > 0:
            msg += f"💰 **Your Buy-ins:**\n"
            if summary["cash_buyins"] > 0:
                msg += f"• Cash: {summary['cash_buyins']}\n"
            if summary["credit_buyins"] > 0:
                msg += f"• Credit: {summary['credit_buyins']}\n"
            msg += f"• **Total: {summary['total_buyins']}**\n\n"

            if summary["pending_debt"] > 0:
                msg += f"💳 **Pending Debt:** {summary['pending_debt']}\n\n"
        else:
            msg += f"💰 No buy-ins yet. Use 'Buy-in' to start playing!\n\n"

        msg += f"🎯 Ready to play!"
        return msg

    def format_game_overview(self, game_status: Dict[str, Any]) -> str:
        """Format game overview message"""
        game = game_status["game"]
        msg = f"🎮 **Game Overview**\n\n"
        msg += f"📋 Code: **{game.code}**\n"
        msg += f"👑 Host: {game.host_name}\n"
        msg += f"👥 Active Players: {game_status['active_players']}\n"
        msg += f"📅 Status: {game.status}\n\n"

        if game_status["total_buyins"] > 0:
            msg += f"💰 **Money in Play:**\n"
            if game_status["total_cash"] > 0:
                msg += f"• Cash: {game_status['total_cash']}\n"
            if game_status["total_credit"] > 0:
                msg += f"• Credit: {game_status['total_credit']}\n"
            msg += f"• **Total: {game_status['total_buyins']}**\n\n"

        msg += f"🎯 Game is active and ready!"
        return msg

    def format_player_list(self, player_data: List[Dict[str, Any]]) -> str:
        """Format player list message"""
        msg = "👥 **Players in game:**\n\n"

        for data in player_data:
            p = data["player"]
            host_indicator = "👑 " if data["is_host"] else ""
            msg += f"• {host_indicator}{p.name} {data['status']}\n"

            if data["total_buyins"] > 0:
                if data["cash_buyins"] > 0 and data["credit_buyins"] > 0:
                    msg += f"  💰 Cash: {data['cash_buyins']} | Credit: {data['credit_buyins']}\n"
                elif data["cash_buyins"] > 0:
                    msg += f"  💵 Cash: {data['cash_buyins']}\n"
                elif data["credit_buyins"] > 0:
                    msg += f"  💳 Credit: {data['credit_buyins']}\n"

            if data["cashout_info"]:
                msg += f"  {data['cashout_info']}\n"

            msg += "\n"

        return msg

    def format_host_status(self, game_status: Dict[str, Any]) -> str:
        """Format host status message"""
        game = game_status["game"]
        msg = f"📊 **Game Status**\n\n"
        msg += f"Code: **{game.code}**\n"
        msg += f"Status: {game.status}\n"
        msg += f"Players: {game_status['active_players']} active\n\n"

        msg += f"💰 **Money Currently in Play:**\n"
        msg += f"• Cash buy-ins: {game_status['total_cash']}\n"
        msg += f"• Credit buy-ins: {game_status['total_credit']}\n"
        msg += f"• Total in play: {game_status['total_buyins']}\n\n"

        if game_status['total_cashed_out'] > 0 or game_status['total_debt_settled'] > 0:
            msg += f"📤 **Already Settled:**\n"
            if game_status['total_cashed_out'] > 0:
                msg += f"• Cashed out: {game_status['total_cashed_out']} chips\n"
            if game_status['total_debt_settled'] > 0:
                msg += f"• Debt settled: {game_status['total_debt_settled']}\n"

        return msg

    def format_cashout_summary(self, user_name: str, summary: Dict[str, Any], chip_count: int) -> str:
        """Format cashout request summary"""
        msg = f"💸 **Cashout Request**\n\n"
        msg += f"Player: {user_name}\n"
        msg += f"Requested chips: {chip_count}\n\n"

        msg += f"💰 **Player's Buy-ins:**\n"
        if summary["cash_buyins"] > 0:
            msg += f"• Cash: {summary['cash_buyins']}\n"
        if summary["credit_buyins"] > 0:
            msg += f"• Credit: {summary['credit_buyins']}\n"
        msg += f"• **Total invested: {summary['total_buyins']}**\n\n"

        if summary["pending_debt"] > 0:
            msg += f"💳 **Outstanding debt: {summary['pending_debt']}**\n\n"

        net_result = chip_count - summary["total_buyins"]
        if net_result > 0:
            msg += f"📈 **Net gain: +{net_result}**"
        elif net_result < 0:
            msg += f"📉 **Net loss: {net_result}**"
        else:
            msg += f"🎯 **Break even**"

        return msg

    def format_cashout_approval_message(self, player_name: str, processing_result: Dict[str, Any]) -> str:
        """Format cashout approval message for host"""
        msg = f"✅ **Approved cashout: {processing_result['chip_count']} chips**\n\n"

        # No debt settlement anymore - player keeps their debts

        total_debt_transferred = sum(t["amount"] for t in processing_result["debt_transfers"])
        if total_debt_transferred > 0:
            msg += f"💳 Debt transferred to player: {total_debt_transferred}\n"
            msg += f"💵 Cash to pay: {processing_result['final_cash']}\n\n"
            msg += f"Debts transferred to {player_name}:\n"
            for transfer in processing_result["debt_transfers"]:
                msg += f"• {transfer['debtor_name']}: {transfer['amount']}\n"
        else:
            msg += f"💵 Cash to pay: {processing_result['final_cash']}\n"

        return msg

    def format_debt_notification(self, debtor_name: str, creditor_name: str, amount: int) -> str:
        """Format debt notification message"""
        return f"💳 You owe {amount} to {creditor_name}"

    def format_credit_notification(self, debtor_name: str, amount: int) -> str:
        """Format credit notification message"""
        return f"💳 {debtor_name} owes you {amount}"

    def format_settlement_data(self, settlement_data: Dict[str, Any]) -> str:
        """Format settlement data message"""
        msg = "⚖️ **Game Settlement**\n\n"

        if settlement_data["settlements"]:
            msg += "**Final Results:**\n"
            for settlement in settlement_data["settlements"]:
                net_indicator = "📈" if settlement["net"] > 0 else "📉" if settlement["net"] < 0 else "🎯"
                msg += f"{net_indicator} {settlement['name']}: {settlement['net']:+d}\n"
                msg += f"   (Chips: {settlement['chips']}, Invested: {settlement['buyins']})\n"

        if settlement_data["debts"]:
            msg += "\n**Outstanding Debts:**\n"
            for debt in settlement_data["debts"]:
                msg += f"💳 {debt['debtor']} owes {debt['amount']} to {debt['creditor']}\n"

        return msg

    def format_general_help(self) -> str:
        """Format general help message"""
        return (
            "🎮 **ChipMate Help**\n\n"
            "**Getting Started:**\n"
            "• `/newgame` - Create a new poker game\n"
            "• `/join CODE` - Join existing game with code\n"
            "• `/status` - Check your current status\n"
            "• `/help` - Show this help\n\n"
            "**Features:**\n"
            "• 💰 Track cash and credit buy-ins\n"
            "• 💸 Handle cashouts with debt settlement\n"
            "• 📱 QR codes for easy joining\n"
            "• ⚖️ Automatic settlement calculations\n\n"
            "Ready to start playing? 🃏"
        )

    def format_player_help(self) -> str:
        """Format player help message"""
        return (
            "🎮 **Player Help**\n\n"
            "**Game Actions:**\n"
            "• `💰 Buy-in` - Add chips (cash or credit)\n"
            "• `💸 Cashout` - Cash out your chips\n"
            "• `🚪 Quit` - Leave the game\n"
            "• `📊 Status` - View your game status\n\n"
            "**Commands:**\n"
            "• `status` - Quick status check\n"
            "• `mygame` - Game overview\n\n"
            "**Note:** Host must approve buy-ins/cashouts!"
        )

    def format_host_help(self) -> str:
        """Format host help message"""
        return (
            "👑 **Host Menu Help**\n\n"
            "**Player Management:**\n"
            "• `👤 Player List` - View all players and their status\n\n"
            "**Transactions:**\n"
            "• `💰 Host Buy-in` - Add buy-in for any player\n"
            "• `💸 Host Cashout` - Add cashout for any player\n\n"
            "**Game Control:**\n"
            "• `⚖️ Settle` - Calculate final settlements\n"
            "• `🔚 End Game` - End the game permanently (appears when all players cashed out)\n"
            "• `📊 Status` - View comprehensive game status\n\n"
            "**Commands:**\n"
            "• `📱 Share QR` - Generate QR code for joining\n"
            "• `📋 Game Report` - Detailed game report\n"
            "• `📈 View Settlement` - Current settlement status"
        )

    def format_rejection_suggestions(self, user_name: str, chip_count: int, suggestions: List[str]) -> str:
        """Format cashout rejection with suggestions"""
        msg = f"❌ **Cashout Rejected: {chip_count} chips**\n\n"
        msg += "💡 **Consider these alternatives:**\n\n"

        for i, suggestion in enumerate(suggestions, 1):
            msg += f"{i}. {suggestion}\n"

        msg += f"\n💬 Talk to the host if you have questions!"
        return msg

    def format_duration(self, duration: timedelta) -> str:
        """Format duration in a readable way"""
        if duration.days > 0:
            return f"{duration.days}d {duration.seconds//3600}h {(duration.seconds//60)%60}m"
        elif duration.seconds >= 3600:
            return f"{duration.seconds//3600}h {(duration.seconds//60)%60}m"
        else:
            return f"{(duration.seconds//60)%60}m {duration.seconds%60}s"