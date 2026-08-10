import os
os.environ["SECRET_KEY"] = "testsecretkey123"
os.environ["VIBECLOUD_FERNET_KEY"] = "I9StON-hofzi783VWEhFYFM1DCXGJc08SBE1olJhDqI="

import pytest
from fastapi import HTTPException
from database.models import User
from main import fix_db

class DummySession:
    pass

def test_fix_db_access_denied_for_normal_user():
    user = User(id=1, username="admin", role="admin", tenant_id=1)
    session = DummySession()
    with pytest.raises(HTTPException) as exc:
        fix_db(session=session, user=user)
    assert exc.value.status_code == 403
    assert exc.value.detail == "Forbidden: Requires superadmin role."

def test_fix_db_access_allowed_for_superadmin():
    user = User(id=1, username="superadmin", role="superadmin", tenant_id=1)
    
    class MockSession:
        def __init__(self):
            self.calls = []
        def exec(self, stmt):
            self.calls.append(stmt)
        def commit(self):
            pass
            
    session = MockSession()
    
    import alembic.command
    original_upgrade = alembic.command.upgrade
    alembic.command.upgrade = lambda *args, **kwargs: None
    
    try:
        response = fix_db(session=session, user=user)
        assert "results" in response
    finally:
        alembic.command.upgrade = original_upgrade
