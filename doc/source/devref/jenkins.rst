Continuous Integration with Jenkins
===================================

Each change made to Stackalytics core code is tested with unit and integration tests and style checks flake8.

Unit tests and style checks are performed on public `OpenStack Jenkins <https://jenkins.openstack.org/>`_ managed by `Zuul <http://status.openstack.org/zuul/>`_.
Unit tests are checked using both python 2.6 and python 2.7.

The result of those checks and Unit tests are +1 or -1 to *Verify* column in a code review from *Jenkins* user.
