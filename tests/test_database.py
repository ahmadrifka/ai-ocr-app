import unittest

from app.database import engine


class DatabaseEngineTests(unittest.TestCase):
    def test_connection_pool_pings_connections_before_reuse(self):
        self.assertTrue(engine.pool._pre_ping)


if __name__ == "__main__":
    unittest.main()
