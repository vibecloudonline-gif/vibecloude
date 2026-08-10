from fastapi.templating import Jinja2Templates
try:
    t = Jinja2Templates(directory="templates")
    t.get_template("dashboard.html")
    print("Dashboard loaded successfully.")
    t.get_template("base.html")
    print("Base loaded successfully.")
    t.get_template("settings.html")
    print("Settings loaded successfully.")
except Exception as e:
    print(f"Error: {e}")
