import jwt
import json
import os
from functools import wraps
import azure.functions as func
from db.mongo import get_db

db = get_db()
blacklist = db.blacklist

def cors_headers():
    return {
        "Access-Control-Allow-Origin": os.environ.get("ALLOWED_ORIGIN"),
        "Access-Control-Allow-Methods": "GET,PUT,POST,DELETE,OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type,Authorization"
    }

def jwt_required(route_function):
    #decorator to check if JWT is valid and not blacklisted
    @wraps(route_function)
    def jwt_required_wrapper(req: func.HttpRequest, *args, **kwargs) -> func.HttpResponse:
        #allow CORS preflight
        if req.method == "OPTIONS":
            return func.HttpResponse(status_code=204)

        #extract token from authorization header
        auth_header = req.headers.get('Authorization')
        token = None
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1].strip()

        if not token:
            return func.HttpResponse(
                json.dumps({'error': 'Token is missing'}),
                mimetype="application/json",
                status_code=401
            )

        # validate token
        secret_key = os.environ.get("JWT_SECRET_KEY")
        if not secret_key:
            return func.HttpResponse(
                json.dumps({'error': 'Server configuration error'}),
                mimetype="application/json",
                status_code=500
            )

        try:
            jwt.decode(token, secret_key, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            return func.HttpResponse(
                json.dumps({'error': 'Token has expired'}),
                mimetype="application/json",
                status_code=401
            )
        except jwt.InvalidTokenError:
            return func.HttpResponse(
                json.dumps({'error': 'Token is invalid'}),
                mimetype="application/json",
                status_code=401
            )

        # check if token is blacklisted
        bl_token = blacklist.find_one({'token': token})
        if bl_token is not None:
            return func.HttpResponse(
                json.dumps({'error': 'Token has been cancelled'}),
                mimetype="application/json",
                status_code=401
            )

        # token is valid, call the original function with token
        setattr(req, "jwt_token", token)
        return route_function(req, *args, **kwargs)
    return jwt_required_wrapper