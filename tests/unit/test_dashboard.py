import os
import tempfile
import unittest

from dashboard import dashboard


class DashboardTestCase(unittest.TestCase):

    def setUp(self):
        self.db_fd, dashboard.app.config['DATABASE'] = tempfile.mkstemp()
        dashboard.app.config['TESTING'] = True
        self.app = dashboard.app.test_client()
        # dashboard.init_db()

    def tearDown(self):
        os.close(self.db_fd)
        os.unlink(dashboard.app.config['DATABASE'])

    def test_home_page(self):
        rv = self.app.get('/')
        assert rv.status_code == 200
