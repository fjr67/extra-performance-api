import os
from pymongo import MongoClient

_client: MongoClient | None = None

def get_client() -> MongoClient:
    global _client
    if _client is None:
        uri = os.environ["MONGODB_URI"]
        _client = MongoClient(uri)
        _client.admin.command("ping") #fail fast if misconfigured
    return _client


def get_db():
    return get_client()["ExtraPerformanceDB"]