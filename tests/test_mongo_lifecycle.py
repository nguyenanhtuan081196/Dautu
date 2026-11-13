import os
import unittest
from unittest.mock import patch

from app.database import mongo


class MongoClientLifecycleTests(unittest.TestCase):
    def tearDown(self):
        mongo.get_client.cache_clear()

    def test_close_client_is_noop_when_client_was_never_created(self):
        with patch("app.database.mongo.MongoClient") as mongo_client:
            mongo.close_client()
        mongo_client.assert_not_called()

    def test_close_client_closes_and_clears_cached_client(self):
        with patch.dict(os.environ, {"MONGODB_URI": "mongodb://localhost:27017"}):
            with patch("app.database.mongo.MongoClient") as mongo_client:
                cached_client = mongo.get_client()
                self.assertIs(cached_client, mongo.get_client())

                mongo.close_client()

        mongo_client.assert_called_once()
        cached_client.close.assert_called_once_with()
        self.assertEqual(mongo.get_client.cache_info().currsize, 0)


if __name__ == "__main__":
    unittest.main()
