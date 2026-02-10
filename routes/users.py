import azure.functions as func
from db.mongo import get_db
import json
import bcrypt
import jwt
import os
import datetime
import base64

bp = func.Blueprint()


@bp.route(route="register", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def registerAccount(req: func.HttpRequest) -> func.HttpResponse:
    #checking for valid JSON body in request
    try:
        data = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Request body must be valid JSON"}),
            mimetype="application/json",
            status_code=400
        )

    #checking required fields are present
    required = ["name", "username", "email", "password"]
    missing = [field for field in required if field not in data]
    if missing:
        return func.HttpResponse(
            json.dumps({"error": "Missing data", "missing": missing}),
            mimetype="application/json",
            status_code=400
        )
    
    #checking required fields have values
    missingFields = []
    if not data["name"].strip() or data["name"] is None:
        missingFields.append("name")
    if not data["username"].strip() or data["username"] is None:
        missingFields.append("username")
    if not data["email"].strip() or data["email"] is None:
        missingFields.append("email")
    if not data["password"].strip() or data["password"] is None:
        missingFields.append("password")

    if missingFields:
        return func.HttpResponse(
            json.dumps({"error": "Missing data", "missing": missingFields}),
            mimetype="application/json",
            status_code=400
        )

    #ensure password is a string
    if not isinstance(data["password"], str):
        return func.HttpResponse(
            json.dumps({"error": "Please enter a string value for password"}),
            mimetype="application/json",
            status_code=400
        )

    db = get_db()
    users = db.users

    #check username does not already exist
    existing = users.find_one({"username": data["username"]})
    if existing:
        return func.HttpResponse(
            json.dumps({"error": "Username already taken"}),
            mimetype="application/json",
            status_code=409
        )
    
    #check email does not already exist
    existing = users.find_one({"email": data["email"]})
    if existing:
        return func.HttpResponse(
            json.dumps({"error": "Account already exists with email: "+data["email"]}),
            mimetype="application/json",
            status_code=409
        )

    #hash password
    hash_pw = bcrypt.hashpw(data["password"].encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    new_user = {
        "name": data["name"],
        "username": data["username"],
        "email": data["email"],
        "password": hash_pw
    }

    users.insert_one(new_user)

    return func.HttpResponse(
        json.dumps({"message": "User created successfully"}),
        mimetype="application/json",
        status_code=201
    )


@bp.route(route="login", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def login(req: func.HttpRequest) -> func.HttpResponse:
    # extract basic auth from Authorization header
    auth_header = req.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Basic "):
        return func.HttpResponse(
            json.dumps({"error": "Authentication required"}),
            mimetype="application/json",
            status_code=401
        )

    # decode base64 credentials
    try:
        encoded = auth_header.split(" ")[1]
        decoded = base64.b64decode(encoded).decode("utf-8")
        username, password = decoded.split(":", 1)
    except (IndexError, ValueError):
        return func.HttpResponse(
            json.dumps({"error": "Invalid authentication format"}),
            mimetype="application/json",
            status_code=401
        )

    db = get_db()
    users = db.users

    # check user exists
    user = users.find_one({"username": username})
    if user is None:
        return func.HttpResponse(
            json.dumps({"error": "Incorrect username"}),
            mimetype="application/json",
            status_code=401
        )

    # check password is correct
    if not bcrypt.checkpw(password.encode("utf-8"), user["password"].encode("utf-8")):
        return func.HttpResponse(
            json.dumps({"error": "Incorrect password"}),
            mimetype="application/json",
            status_code=401
        )

    # generate JWT token
    secret_key = os.environ.get("JWT_SECRET_KEY")
    if not secret_key:
        return func.HttpResponse(
            json.dumps({"error": "Server configuration error"}),
            mimetype="application/json",
            status_code=500
        )

    token = jwt.encode(
        {
            "user": username,
            "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=60)
        },
        secret_key,
        algorithm="HS256"
    )

    return func.HttpResponse(
        json.dumps({"token": token}),
        mimetype="application/json",
        status_code=200
    )


@bp.route(route="logout", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def logout(req: func.HttpRequest) -> func.HttpResponse:
    # extract token from header
    token = req.headers.get("x-access-token")
    if not token:
        return func.HttpResponse(
            json.dumps({"error": "Token required"}),
            mimetype="application/json",
            status_code=401
        )

    # validate token signature
    secret_key = os.environ.get("JWT_SECRET_KEY")
    if not secret_key:
        return func.HttpResponse(
            json.dumps({"error": "Server configuration error"}),
            mimetype="application/json",
            status_code=500
        )

    try:
        jwt.decode(token, secret_key, algorithms=["HS256"])
    except jwt.InvalidTokenError:
        return func.HttpResponse(
            json.dumps({"error": "Invalid token"}),
            mimetype="application/json",
            status_code=401
        )

    # add token to blacklist
    db = get_db()
    blacklist = db.blacklist
    blacklist.insert_one({"token": token})

    return func.HttpResponse(
        json.dumps({"message": "Logout successful"}),
        mimetype="application/json",
        status_code=200
    )
