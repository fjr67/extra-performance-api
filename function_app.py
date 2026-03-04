import azure.functions as func
import datetime
import json
import logging
from routes.events import bp as events_bp
from routes.users import bp as users_bp
from routes.workouts import bp as workouts_bp
from routes.exercises import bp as exercises_bp
from routes.goals import bp as goals_bp

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

app.register_blueprint(events_bp)
app.register_blueprint(users_bp)
app.register_blueprint(workouts_bp)
app.register_blueprint(exercises_bp)
app.register_blueprint(goals_bp)