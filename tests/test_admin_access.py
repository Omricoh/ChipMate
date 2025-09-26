import pytest
import os
import mongomock
from src.models.game import Game
from src.dal.games_dal import GamesDAL


@pytest.fixture
def mock_db():
    """Create a fake in-memory MongoDB using mongomock."""
    client = mongomock.MongoClient()
    return client["chipbot_test"]


@pytest.fixture
def games_dal(mock_db):
    return GamesDAL(mock_db)


def test_list_games_without_admin_env(games_dal):
    """Test that list_games works when no admin credentials are set."""
    # Create some test games
    game1 = Game(host_id=1, host_name="Alice", code="ABC12")
    game2 = Game(host_id=2, host_name="Bob", code="XYZ99")

    games_dal.create(game1)
    games_dal.create(game2)

    # Without env vars set, should work without auth
    games = games_dal.list_games()
    assert len(games) == 2


def test_list_games_with_admin_auth(games_dal, monkeypatch):
    """Test that list_games requires correct admin credentials when set."""
    # Set admin credentials
    monkeypatch.setenv("ADMIN_USER", "admin")
    monkeypatch.setenv("ADMIN_PASS", "secret123")

    # Create some test games
    game1 = Game(host_id=1, host_name="Alice", code="ABC12")
    games_dal.create(game1)

    # Without credentials - should fail
    with pytest.raises(PermissionError, match="Unauthorized"):
        games_dal.list_games()

    # With wrong credentials - should fail
    with pytest.raises(PermissionError, match="Unauthorized"):
        games_dal.list_games(user="wrong", password="wrong")

    # With correct credentials - should succeed
    games = games_dal.list_games(user="admin", password="secret123")
    assert len(games) == 1
    assert games[0].host_name == "Alice"


def test_admin_access_isolation(games_dal):
    """Test that admin access doesn't affect other DAL methods."""
    # Regular operations should work without admin credentials
    game = Game(host_id=3, host_name="Charlie", code="TEST1")
    game_id = games_dal.create(game)

    # These should work without auth
    assert games_dal.get_by_code("TEST1") is not None
    assert games_dal.get_game(game_id) is not None
    assert games_dal.get_host_id(game_id) == 3

    # Add player should work
    games_dal.add_player(game_id, 100)

    # Update status should work
    games_dal.update_status(game_id, "ended")
    updated = games_dal.get_game(game_id)
    assert updated.status == "ended"