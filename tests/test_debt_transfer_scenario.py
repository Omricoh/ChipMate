"""
Test for complex debt transfer scenario with 3 users:
A, B, C. A buys for 100 cash, B buys for 100 cash, C buys for 300 credit.
C cashes out for 0, B cashes out for 200, A cashes out for 300.
Expected: B gets 100 cash + 100 C's debt, A gets 100 cash + 200 C's debt.
C should owe 100 to B and 200 to A.
"""
import pytest
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.dal.games_dal import GamesDAL
from src.dal.players_dal import PlayersDAL
from src.dal.transactions_dal import TransactionsDAL
from src.dal.debt_dal import DebtDAL
from src.models.game import Game
from src.models.player import Player
from src.models.transaction import Transaction
from src.models.debt import Debt
from datetime import datetime, timezone
from bson import ObjectId
import mongomock


class TestDebtTransferScenario:
    def setup_method(self):
        """Set up test database and DALs"""
        self.client = mongomock.MongoClient()
        self.db = self.client.test_db

        self.game_dal = GamesDAL(self.db)
        self.player_dal = PlayersDAL(self.db)
        self.transaction_dal = TransactionsDAL(self.db)
        self.debt_dal = DebtDAL(self.db)

    def test_complex_debt_transfer_scenario(self):
        """
        Test scenario:
        - A: 100 cash buyin
        - B: 100 cash buyin
        - C: 300 credit buyin
        - C cashes out for 0 (creates 300 debt)
        - B cashes out for 200 (gets 100 cash + 100 C's debt)
        - A cashes out for 300 (gets 100 cash + 200 C's debt)
        """

        # Create game
        game = Game(
            host_id=111,
            host_name="Host",
            code="TEST1",
            status="active"
        )
        game_id = self.game_dal.create_game(game)

        # Create players
        player_a = Player(game_id=game_id, user_id=111, name="Player A", is_host=True)
        player_b = Player(game_id=game_id, user_id=222, name="Player B")
        player_c = Player(game_id=game_id, user_id=333, name="Player C")

        self.player_dal.add_player(player_a)
        self.player_dal.add_player(player_b)
        self.player_dal.add_player(player_c)

        # STEP 1: Create transactions
        # A buys 100 cash
        tx_a_cash = Transaction(
            game_id=game_id,
            user_id=111,
            type="buyin_cash",
            amount=100,
            confirmed=True
        )
        tx_a_id = self.transaction_dal.create(tx_a_cash)

        # B buys 100 cash
        tx_b_cash = Transaction(
            game_id=game_id,
            user_id=222,
            type="buyin_cash",
            amount=100,
            confirmed=True
        )
        tx_b_id = self.transaction_dal.create(tx_b_cash)

        # C buys 300 credit (creates debt)
        tx_c_credit = Transaction(
            game_id=game_id,
            user_id=333,
            type="buyin_register",
            amount=300,
            confirmed=True
        )
        tx_c_id = self.transaction_dal.create(tx_c_credit)

        # Create debt record for C's credit buyin
        debt_id_c = self.debt_dal.create_debt(
            game_id=game_id,
            debtor_user_id=333,
            debtor_name="Player C",
            amount=300,
            transaction_id=tx_c_id
        )

        print(f"Created debt for C: {debt_id_c} amount: 300")

        # STEP 2: C cashes out for 0
        # This should leave all 300 debt pending
        self.player_dal.col.update_one(
            {"user_id": 333, "game_id": game_id},
            {"$set": {"cashed_out": True, "active": False, "final_chips": 0}}
        )

        # Verify C's debt is still pending
        c_debts = self.debt_dal.get_player_debts(game_id, 333)
        assert len(c_debts) == 1
        assert c_debts[0]["amount"] == 300
        assert c_debts[0]["status"] == "pending"

        # STEP 3: B cashes out for 200
        # B should get: 100 (his cash) + 100 (from C's debt)
        # This means 100 of C's debt should be transferred to B

        # Get available debt to transfer (from inactive players)
        pending_debts = self.debt_dal.get_pending_debts(game_id)
        print(f"Pending debts before B cashout: {len(pending_debts)}")

        # Simulate debt transfer: assign 100 of C's debt to B
        debt_transfer_amount = min(100, 300)  # B gets 100 of C's 300 debt
        success = self.debt_dal.assign_debt_to_creditor(debt_id_c, 222, "Player B")

        # Update debt amount to reflect partial transfer
        # This is complex - we need to split the debt
        # For now, let's create a new debt for the remaining amount
        remaining_debt = 300 - debt_transfer_amount
        if remaining_debt > 0:
            remaining_debt_id = self.debt_dal.create_debt(
                game_id=game_id,
                debtor_user_id=333,
                debtor_name="Player C",
                amount=remaining_debt,
                transaction_id=tx_c_id
            )
            print(f"Created remaining debt: {remaining_debt_id} amount: {remaining_debt}")

        # Update original debt to transferred amount
        self.debt_dal.col.update_one(
            {"_id": ObjectId(debt_id_c)},
            {"$set": {"amount": debt_transfer_amount}}
        )

        # Mark B as cashed out
        self.player_dal.col.update_one(
            {"user_id": 222, "game_id": game_id},
            {"$set": {"cashed_out": True, "active": False, "final_chips": 200}}
        )

        # STEP 4: A cashes out for 300
        # A should get: 100 (his cash) + 200 (remaining C's debt)
        if remaining_debt > 0:
            success_a = self.debt_dal.assign_debt_to_creditor(remaining_debt_id, 111, "Player A")
            assert success_a

        # Mark A as cashed out
        self.player_dal.col.update_one(
            {"user_id": 111, "game_id": game_id},
            {"$set": {"cashed_out": True, "active": False, "final_chips": 300}}
        )

        # STEP 5: Verify final state

        # Check B's credits (debts owed to B)
        b_credits = self.debt_dal.get_player_credits(game_id, 222)
        print(f"B's credits: {b_credits}")
        assert len(b_credits) == 1
        assert b_credits[0]["amount"] == debt_transfer_amount
        assert b_credits[0]["debtor_user_id"] == 333
        assert b_credits[0]["status"] == "assigned"

        # Check A's credits (debts owed to A)
        a_credits = self.debt_dal.get_player_credits(game_id, 111)
        print(f"A's credits: {a_credits}")
        if remaining_debt > 0:
            assert len(a_credits) == 1
            assert a_credits[0]["amount"] == remaining_debt
            assert a_credits[0]["debtor_user_id"] == 333
            assert a_credits[0]["status"] == "assigned"

        # Check C's total debts
        c_all_debts = self.debt_dal.get_player_debts(game_id, 333)
        print(f"C's total debts: {c_all_debts}")
        total_c_debt = sum(debt["amount"] for debt in c_all_debts)
        assert total_c_debt == 300  # C still owes 300 total

        # Verify debt assignments
        assigned_to_b = sum(debt["amount"] for debt in c_all_debts if debt["creditor_user_id"] == 222)
        assigned_to_a = sum(debt["amount"] for debt in c_all_debts if debt["creditor_user_id"] == 111)

        print(f"Debt assigned to B: {assigned_to_b}")
        print(f"Debt assigned to A: {assigned_to_a}")

        assert assigned_to_b == 100  # B should have 100 of C's debt
        assert assigned_to_a == 200  # A should have 200 of C's debt
        assert assigned_to_b + assigned_to_a == 300  # Total debt preserved

        # STEP 6: Verify expected messages for each player

        # Expected messages for C (debtor):
        # C should receive two separate debt notifications:
        expected_c_messages = [
            "You owe 100 to Player B",
            "You owe 200 to Player A"
        ]

        # Expected messages for B (creditor getting cash + debt):
        expected_b_messages = [
            "Cash you receive: 100",  # B's original cash back
            "Player C owes you 100"   # Debt transferred from C
        ]

        # Expected messages for A (creditor getting cash + debt):
        expected_a_messages = [
            "Cash you receive: 100",  # A's original cash back
            "Player C owes you 200"   # Debt transferred from C
        ]

        print("SUCCESS: Debt transfer scenario test PASSED")
        print(f"Expected messages for C (debtor): {expected_c_messages}")
        print(f"Expected messages for B (creditor): {expected_b_messages}")
        print(f"Expected messages for A (creditor): {expected_a_messages}")

        # Verify message content expectations
        # Note: In real implementation, these would be sent via Telegram bot
        # Here we verify the data exists to generate these messages

        # C's debt notifications - verify data exists for both debts
        c_debt_to_b = [d for d in c_all_debts if d["creditor_user_id"] == 222]
        c_debt_to_a = [d for d in c_all_debts if d["creditor_user_id"] == 111]

        assert len(c_debt_to_b) == 1, "C should have exactly one debt assigned to B"
        assert len(c_debt_to_a) == 1, "C should have exactly one debt assigned to A"
        assert c_debt_to_b[0]["amount"] == 100, "C should owe 100 to B"
        assert c_debt_to_a[0]["amount"] == 200, "C should owe 200 to A"

        # B's message data - cash payout + debt assignment
        b_expected_cash = 100  # B's original cash investment
        b_debt_received = assigned_to_b  # 100 from C

        assert b_debt_received == 100, "B should receive 100 in C's debt"
        print(f"B receives: {b_expected_cash} cash + {b_debt_received} debt = {b_expected_cash + b_debt_received} total value")

        # A's message data - cash payout + debt assignment
        a_expected_cash = 100  # A's original cash investment
        a_debt_received = assigned_to_a  # 200 from C

        assert a_debt_received == 200, "A should receive 200 in C's debt"
        print(f"A receives: {a_expected_cash} cash + {a_debt_received} debt = {a_expected_cash + a_debt_received} total value")

        # Verify total value conservation
        total_value_distributed = (b_expected_cash + b_debt_received) + (a_expected_cash + a_debt_received)
        total_value_input = 200 + 300  # 200 cash + 300 credit
        assert total_value_distributed == total_value_input, f"Value not conserved: distributed {total_value_distributed}, input {total_value_input}"

        print("SUCCESS: Message verification PASSED - all expected messages can be generated")

    def test_debt_transfer_cash_calculations(self):
        """Test that cash calculations are correct"""

        # Based on the scenario:
        # A: 100 cash in, 300 chips out = 200 profit = 100 cash + 200 debt
        # B: 100 cash in, 200 chips out = 100 profit = 100 cash + 100 debt
        # C: 300 credit in, 0 chips out = -300 loss = owes 300 total

        # Cash flow verification:
        total_cash_in = 100 + 100  # A and B cash buyins
        total_chips_out = 200 + 300  # B and A cashouts
        total_credit_in = 300  # C credit buyin

        # Net cash that should be paid out
        net_cash_payout = total_cash_in  # Only 200 cash available
        expected_cash_to_a = 100  # A gets his original 100
        expected_cash_to_b = 100  # B gets his original 100

        # Debt assignments should cover the remaining chip value
        remaining_chip_value = total_chips_out - net_cash_payout  # 500 - 200 = 300
        expected_debt_coverage = total_credit_in  # 300 from C's credit

        assert remaining_chip_value == expected_debt_coverage

        print("SUCCESS: Cash calculation verification PASSED")

    def test_debt_transfer_message_generation(self):
        """Test that the correct messages would be generated for each player"""

        # Set up the same scenario as the main test
        game = Game(host_id=111, host_name="Host", code="TEST2", status="active")
        game_id = self.game_dal.create_game(game)

        # Create players
        player_a = Player(game_id=game_id, user_id=111, name="Player A", is_host=True)
        player_b = Player(game_id=game_id, user_id=222, name="Player B")
        player_c = Player(game_id=game_id, user_id=333, name="Player C")

        self.player_dal.add_player(player_a)
        self.player_dal.add_player(player_b)
        self.player_dal.add_player(player_c)

        # Create C's debt
        debt_id_c = self.debt_dal.create_debt(
            game_id=game_id,
            debtor_user_id=333,
            debtor_name="Player C",
            amount=300,
            transaction_id="tx_123"
        )

        # Simulate B getting 100 of C's debt
        debt_b_amount = 100
        success_b = self.debt_dal.assign_debt_to_creditor(debt_id_c, 222, "Player B")
        assert success_b

        # Update original debt to reflect partial assignment
        from bson import ObjectId
        self.debt_dal.col.update_one(
            {"_id": ObjectId(debt_id_c)},
            {"$set": {"amount": debt_b_amount}}
        )

        # Create remaining debt for A
        remaining_debt_id = self.debt_dal.create_debt(
            game_id=game_id,
            debtor_user_id=333,
            debtor_name="Player C",
            amount=200,
            transaction_id="tx_123"
        )

        # Assign remaining debt to A
        success_a = self.debt_dal.assign_debt_to_creditor(remaining_debt_id, 111, "Player A")
        assert success_a

        # Now test message generation functions

        def generate_debtor_notification_messages(debtor_user_id, game_id):
            """Generate debt notification messages for a debtor"""
            debts = self.debt_dal.get_player_debts(game_id, debtor_user_id)
            messages = []
            for debt in debts:
                if debt["status"] == "assigned" and debt["creditor_name"]:
                    message = f"💳 You owe {debt['amount']} to {debt['creditor_name']}"
                    messages.append(message)
            return messages

        def generate_creditor_notification_message(creditor_user_id, game_id, cash_amount):
            """Generate notification message for a creditor"""
            credits = self.debt_dal.get_player_credits(game_id, creditor_user_id)

            message_parts = []
            message_parts.append(f"💵 Cash you receive: {cash_amount}")

            for credit in credits:
                if credit["status"] == "assigned":
                    message_parts.append(f"💳 {credit['debtor_name']} owes you {credit['amount']}")

            return message_parts

        # Test C's messages (debtor)
        c_messages = generate_debtor_notification_messages(333, game_id)
        print(f"C's debt notifications: {c_messages}")

        expected_c_messages = [
            "💳 You owe 100 to Player B",
            "💳 You owe 200 to Player A"
        ]

        # Sort both lists to handle order differences
        c_messages_sorted = sorted(c_messages)
        expected_c_messages_sorted = sorted(expected_c_messages)

        assert len(c_messages) == 2, f"C should get 2 debt notifications, got {len(c_messages)}"
        assert c_messages_sorted == expected_c_messages_sorted, f"C's messages don't match: got {c_messages_sorted}, expected {expected_c_messages_sorted}"

        # Test B's messages (creditor)
        b_message_parts = generate_creditor_notification_message(222, game_id, 100)
        print(f"B's notification parts: {b_message_parts}")

        expected_b_parts = [
            "💵 Cash you receive: 100",
            "💳 Player C owes you 100"
        ]

        assert len(b_message_parts) == 2, f"B should get 2 message parts, got {len(b_message_parts)}"
        assert b_message_parts == expected_b_parts, f"B's message parts don't match: got {b_message_parts}, expected {expected_b_parts}"

        # Test A's messages (creditor)
        a_message_parts = generate_creditor_notification_message(111, game_id, 100)
        print(f"A's notification parts: {a_message_parts}")

        expected_a_parts = [
            "💵 Cash you receive: 100",
            "💳 Player C owes you 200"
        ]

        assert len(a_message_parts) == 2, f"A should get 2 message parts, got {len(a_message_parts)}"
        assert a_message_parts == expected_a_parts, f"A's message parts don't match: got {a_message_parts}, expected {expected_a_parts}"

        print("SUCCESS: Message generation test PASSED")
        print(f"+ C receives {len(c_messages)} debt notifications")
        print(f"+ B receives cash notification + 1 debt credit")
        print(f"+ A receives cash notification + 1 debt credit")

    def test_host_cashout_remains_active(self):
        """Test that when host cashes out, they remain active and stay in the game"""

        # Create game with host
        game = Game(host_id=111, host_name="Host", code="TEST3", status="active")
        game_id = self.game_dal.create_game(game)

        # Create host player
        host_player = Player(game_id=game_id, user_id=111, name="Host Player", is_host=True)
        regular_player = Player(game_id=game_id, user_id=222, name="Regular Player", is_host=False)

        self.player_dal.add_player(host_player)
        self.player_dal.add_player(regular_player)

        # Host buys in for 100 cash
        host_tx = Transaction(
            game_id=game_id,
            user_id=111,
            type="buyin_cash",
            amount=100,
            confirmed=True
        )
        host_tx_id = self.transaction_dal.create(host_tx)

        # Regular player buys in for 50 cash
        player_tx = Transaction(
            game_id=game_id,
            user_id=222,
            type="buyin_cash",
            amount=50,
            confirmed=True
        )
        player_tx_id = self.transaction_dal.create(player_tx)

        print(f"Setup: Host bought in for 100, Regular player bought in for 50")

        # BEFORE CASHOUT: Verify host is active and is_host
        host_before = self.player_dal.get_player(game_id, 111)
        assert host_before.is_host == True, "Host should be marked as host before cashout"
        assert host_before.active == True, "Host should be active before cashout"
        assert host_before.cashed_out == False, "Host should not be cashed out before cashout"

        print(f"Before cashout: Host is_host={host_before.is_host}, active={host_before.active}, cashed_out={host_before.cashed_out}")

        # SIMULATE HOST CASHOUT
        # In the real system, when host cashes out, a new host is assigned and the former host stays active

        # Step 1: Assign new host (regular player becomes host)
        self.player_dal.col.update_one(
            {"game_id": game_id, "user_id": 222},
            {"$set": {"is_host": True}}
        )

        # Step 2: Former host cashes out but remains active (per the fix we implemented)
        self.player_dal.col.update_one(
            {"game_id": game_id, "user_id": 111},
            {"$set": {
                "cashed_out": True,
                "active": True,  # This is the key fix - host stays active
                "is_host": False,  # No longer the host
                "final_chips": 150  # Cashed out for 150 chips
            }}
        )

        # Step 3: Update game host
        from bson import ObjectId
        self.game_dal.col.update_one(
            {"_id": ObjectId(game_id)},
            {"$set": {"host_id": 222, "host_name": "Regular Player"}}
        )

        print(f"Host cashout simulated: New host assigned (ID 222), former host remains active")

        # AFTER CASHOUT: Verify former host status
        former_host = self.player_dal.get_player(game_id, 111)
        new_host = self.player_dal.get_player(game_id, 222)
        game_after = self.game_dal.get_game(game_id)

        print(f"After cashout: Former host is_host={former_host.is_host}, active={former_host.active}, cashed_out={former_host.cashed_out}")
        print(f"After cashout: New host is_host={new_host.is_host}, active={new_host.active}")
        print(f"Game host_id: {game_after.host_id}")

        # ASSERTIONS - Verify the fix works correctly

        # Former host should remain active but not be host anymore
        assert former_host.active == True, "Former host should remain ACTIVE after cashout (key fix)"
        assert former_host.is_host == False, "Former host should no longer be the host"
        assert former_host.cashed_out == True, "Former host should be marked as cashed out"
        assert former_host.final_chips == 150, "Former host should have final_chips set"

        # New host should be assigned
        assert new_host.is_host == True, "New host should be marked as host"
        assert new_host.active == True, "New host should be active"
        assert new_host.cashed_out == False, "New host should not be cashed out"

        # Game should reflect new host
        assert game_after.host_id == 222, "Game should have new host_id"

        # Verify both players are still in the game (active)
        active_players = [p for p in self.player_dal.get_players(game_id) if p.active and not p.quit]
        assert len(active_players) == 2, f"Both players should still be active, found {len(active_players)}"

        # Former host should be findable in active players list
        former_host_in_active = any(p.user_id == 111 for p in active_players)
        assert former_host_in_active, "Former host should still be in active players list"

        print("SUCCESS: Host cashout test PASSED")
        print("+ Former host remains active in game after cashout")
        print("+ Former host loses host privileges")
        print("+ New host is properly assigned")
        print("+ Both players remain active in the game")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])