import os, logging
import azure.functions as func
from db.mongo import get_db
import json
from decorators import jwt_required
from bson import ObjectId
from bson.errors import InvalidId
from datetime import datetime
import jwt

bp = func.Blueprint()

#helper to decode JWT token
def decodeToken(token):
    decoded = jwt.decode(
        token,
        os.environ.get("JWT_SECRET_KEY"),
        algorithms=["HS256"]
    )
    return decoded.get("userId")

@bp.route(route="v1.0/goals", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
@jwt_required
def get_goals(req: func.HttpRequest) -> func.HttpResponse:
    db = get_db()
    goals = db.goals

    #getting userId from token and validating
    token = getattr(req, "jwt_token", None)

    try:
        user_id = ObjectId(decodeToken(token))
    except (InvalidId, TypeError):
        return func.HttpResponse(
            json.dumps({"error": "Invalid userId in token"}),
            mimetype="application/json",
            status_code=401
        )

    if not user_id:
        return func.HttpResponse(
            json.dumps({'error': 'userId is missing'}),
            mimetype="application/json",
            status_code=400
        )

    user_goals = list(goals.find({"userId": user_id}))

    for goal in user_goals:
        goal["_id"] = str(goal["_id"])
        goal["userId"] = str(goal["userId"])

    return func.HttpResponse(
        body=json.dumps(user_goals),
        mimetype="application/json",
        status_code=200
    )


@bp.route(route="v1.0/createGoal", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
@jwt_required
def create_goal(req: func.HttpRequest) -> func.HttpResponse:
    db = get_db()
    goals = db.goals
    users = db.users

    goalTypes = ["TOTAL_WORKOUTS", "TOTAL_WEIGHT_LIFTED"]

    #checking for valid JSON body in request
    try:
        data = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Request body must be valid JSON"}),
            mimetype="application/json",
            status_code=400
        )
    
    if not isinstance(data, dict):
        return func.HttpResponse(
            json.dumps({"error": "Request body must be a valid JSON object"}),
            mimetype="application/json",
            status_code=400
        )
    
    if not data:
        return func.HttpResponse(
            json.dumps({"error": "Request body cannot be empty"}),
            mimetype="application/json",
            status_code=400
        )

    #getting userId from token and validating
    token = getattr(req, "jwt_token", None)

    try:
        user_id = ObjectId(decodeToken(token))
    except (InvalidId, TypeError):
        return func.HttpResponse(
            json.dumps({"error": "Invalid userId in token"}),
            mimetype="application/json",
            status_code=401
        )
    
    #checking userId exists
    existing = users.find_one({"_id": user_id})
    if not existing:
        return func.HttpResponse(
            json.dumps({"error": "userId does not exist"}),
            mimetype="application/json",
            status_code=403
        )
    
    required = {"type", "target"}
    missing = [field for field in required if field not in data]
    if missing:
        return func.HttpResponse(
            json.dumps({"error": "Missing data", "missing": missing}),
            mimetype="application/json",
            status_code=400
        )
    
    if data["type"] not in goalTypes:
        return func.HttpResponse(
            json.dumps({"error": 'type must be "TOTAL_WORKOUTS" or "TOTAL_WEIGHT_LIFTED"'}),
            mimetype="application/json",
            status_code=400
        )
    
    try:
        goalTarget = float(data["target"])
    except (TypeError, ValueError):
        return func.HttpResponse(
            json.dumps({"error": 'target must be a number'}),
            mimetype="application/json",
            status_code=400
        )
    
    if goalTarget < 1 or goalTarget > 10000000:
        return func.HttpResponse(
            json.dumps({"error": 'target must be between 1 and 10000000'}),
            mimetype="application/json",
            status_code=400
        )
    
    new_goal = {
        'userId': user_id,
        'type': data["type"],
        'target': goalTarget
    }

    result = goals.insert_one(new_goal)
    goalId = result.inserted_id

    return func.HttpResponse(
        json.dumps({"message": "Goal created", "id": str(goalId)}),
        mimetype="application/json",
        status_code=201
    )


@bp.route(route="v1.0/workoutsProgress", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
@jwt_required
def get_total_workouts_progress(req: func.HttpRequest) -> func.HttpResponse:
    db = get_db()
    workouts = db.workoutLogs

    #getting userId from token and validating
    token = getattr(req, "jwt_token", None)

    try:
        user_id = ObjectId(decodeToken(token))
    except (InvalidId, TypeError):
        return func.HttpResponse(
            json.dumps({"error": "Invalid userId in token"}),
            mimetype="application/json",
            status_code=401
        )

    if not user_id:
        return func.HttpResponse(
            json.dumps({'error': 'userId is missing'}),
            mimetype="application/json",
            status_code=400
        )
    
    current = workouts.count_documents({"userId": user_id})

    return func.HttpResponse(
        json.dumps({"current": current}),
        mimetype="application/json",
        status_code=200
    )


@bp.route(route="v1.0/weightProgress", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
@jwt_required
def get_total_weight_progress(req: func.HttpRequest) -> func.HttpResponse:
    db = get_db()
    workouts = db.workoutLogs

    #getting userId from token and validating
    token = getattr(req, "jwt_token", None)

    try:
        user_id = ObjectId(decodeToken(token))
    except (InvalidId, TypeError):
        return func.HttpResponse(
            json.dumps({"error": "Invalid userId in token"}),
            mimetype="application/json",
            status_code=401
        )

    if not user_id:
        return func.HttpResponse(
            json.dumps({'error': 'userId is missing'}),
            mimetype="application/json",
            status_code=400
        )
    
    pipeline = [
        {"$match": {"userId": user_id}},
        {"$unwind": "$exercises"},
        {"$unwind": "$exercises.sets"},
        {"$group": {
            "_id": None,
            "total": {
                "$sum": {
                    "$multiply": ["$exercises.sets.reps", "$exercises.sets.weight"]
                }
            }
        }}
    ]

    result = list(workouts.aggregate(pipeline))
    if result and result[0].get("total") is not None:
        total = float(result[0]["total"])
    else:
        total = 0.0

    return func.HttpResponse(
        json.dumps({"current": total}),
        mimetype="application/json",
        status_code=200
    )