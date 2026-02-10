import azure.functions as func
import datetime
import json
import logging
from routes.events import bp as events_bp
from routes.users import bp as users_bp

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

app.register_blueprint(events_bp)
app.register_blueprint(users_bp)

