import pytest
import mongomock
from src.models.game import Game
from src.models.player import Player
from src.models.transaction import Transaction
from src.dal.games_dal import GamesDAL
from src.dal.players_dal import PlayersDAL
from src.dal.transactions_dal import TransactionsDAL


@pytest.fixture
def mock_db():
    """Create a fake in-memory MongoDB using mongomock."""
    client = mongomock.MongoClient()
    return client["chipbot_test"]


@pytest.fixture
def games_dal(mock_db):
    return GamesDAL(mock_db)


@pytest.fixture
def players_dal(mock_db):
    return PlayersDAL(mock_db)


@pytest.fixture
def transactions_dal(mock_db):
    return TransactionsDAL(mock_db)


def test_create_game_and_host_is_player(games_dal, players_dal):
    game = Game(host_id=1, host_name="Alice", code="ABCDE")
    game_id = games_dal.create(game)

    assert len(games_dal.list_games()) == 1
    saved_game = games_dal.get_by_code("ABCDE")
    assert saved_game.host_id == 1
    assert saved_game.status == "active"

    # host joins as player
    player = Player(game_id=game_id, user_id=1, name="Alice", is_host=True)
    players_dal.upsert(player)
    saved_player = players_dal.get_player(game_id, 1)
    assert saved_player.is_host
    assert saved_player.active


def test_player_join_and_leave(players_dal, games_dal):
    game = Game(host_id=2, host_name="Bob", code="XYZ12")
    game_id = games_dal.create(game)

    p1 = Player(game_id=game_id, user_id=100, name="Charlie")
    players_dal.add_player(p1)

    assert len(players_dal.get_players(game_id)) == 1

    players_dal.remove_player(game_id, 100)
    assert len(players_dal.get_players(game_id)) == 0


def test_game_status_changes(games_dal):
    game = Game(host_id=3, host_name="Dana", code="PQRS1")
    game_id = games_dal.create_game(game)

    # Active → Finished
    games_dal.update_status(game_id, "finished")
    saved = games_dal.get_game(game_id)
    assert saved.status == "finished"

    # Finished → Cancelled
    games_dal.update_status(game_id, "cancelled")
    saved = games_dal.get_game(game_id)
    assert saved.status == "cancelled"


def test_transactions_flow(transactions_dal, games_dal):
    game = Game(host_id=4, host_name="Eve", code="LMN45")
    game_id = games_dal.create_game(game)

    tx = Transaction(game_id=game_id, user_id=10, type="buyin_cash", amount=200)
    tx_id = transactions_dal.add_transaction(tx)

    saved = transactions_dal.get_transaction(tx_id)
    assert saved.type == "buyin_cash"
    assert saved.amount == 200
    assert not saved.confirmed

    # confirm it
    transactions_dal.confirm_transaction(tx_id)
    confirmed_tx = transactions_dal.get_transaction(tx_id)
    assert confirmed_tx.confirmed

    # reject it
    transactions_dal.reject_transaction(tx_id)
    rejected_tx = transactions_dal.get_transaction(tx_id)
    assert rejected_tx.rejected
