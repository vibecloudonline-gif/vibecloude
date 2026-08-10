from database.session import get_session
from sqlmodel import Session, select
from database.models import User, Tenant, Settings
import os

try:
    with next(get_session()) as session:
        # Simulate getting settings
        from services.settings_service import SettingsService
        # If tenant is 1
        settings = SettingsService.get_or_create_settings(session, tenant_id=1)
        print("Settings fetched:", settings.ui_theme)
except Exception as e:
    import traceback
    traceback.print_exc()
