import jwt
import json
import os
from functools import wraps
import azure.functions as func
from db.mongo import get_db

db = get_db()
blacklist = db.blacklist

def jwt_required(route_function):
    #decorator to check if JWT is valid and not blacklisted
    @wraps(route_function)
    def jwt_required_wrapper(req: func.HttpRequest) -> func.HttpResponse:
        #extract token from header
        token = None
        if 'x-access-token' in req.headers:
            token = req.headers.get('x-access-token')
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
            data = jwt.decode(token, secret_key, algorithms=["HS256"])
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

        # token is valid, call the original function
        return route_function(req)
    return jwt_required_wrapper