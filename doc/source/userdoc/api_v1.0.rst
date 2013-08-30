Stackalytics JSON API v1.0
**************************

.. note::

    JSON API v1.0 corresponds to Stackalytics v0.2.X

1 General API information
=========================

This section contains base info about the Stackalytics JSON API design.


1.2 Request / Response Types
----------------------------

The Stackalytics API supports the JSON data serialization format.
This means that for requests that contain a body, the Content-Type header must be set to the MIME type value
"application/json". Also, clients should accept JSON serialized responses by specifying the Accept header
with the MIME type value "application/json" or adding ".json" extension to the resource name.
The default response format is "application/json" if the client omits to specify an Accept header
or append the ".json" extension in the URL path.

Example:

.. sourcecode:: http

    GET /v1.0/data/companies.json

or

.. sourcecode:: http

    GET /v1.0/data/companies
    Accept: application/json

1.3 Faults
----------

The Stackalytics API returns an error response if a failure occurs while processing a request.
Stackalytics uses only standard HTTP error codes. 4xx errors indicate problems in the particular
request being sent from the client and 5xx errors indicate server-side problems.


2 Metrics
=========

**Description**

Get different metrics.

**Plugins ops**

+-----------------+-------------------------------------------------------------------+-----------------------------------------------------+
| Verb            | URI                                                               | Description                                         |
+=================+===================================================================+=====================================================+
| GET             | /v1.0/data/companies                                              | Contribution by companies.                          |
+-----------------+-------------------------------------------------------------------+-----------------------------------------------------+

