"""
Core Google Workspace helpers backing the generated ``gsuite_<service>`` modules.

This module is hand written (everything else under ``modules/`` is generated). It exposes:

* ``gsuite.version`` - report the extension version and the bundled ``gws`` CLI version,
* ``gsuite.call`` - a generic escape hatch to invoke any ``gws`` method directly,
* ``gsuite.auth_test`` - validate the configured credentials with a cheap authenticated call.

CLI Examples:

.. code-block:: bash

    salt '*' gsuite.version
    salt '*' gsuite.auth_test
    salt '*' gsuite.call drive files list params='{"pageSize": 5}'
"""

import logging

import saltext.gsuite
from saltext.gsuite import _binary
from saltext.gsuite import _gws

log = logging.getLogger(__name__)

__virtualname__ = "gsuite"


def __virtual__():
    return __virtualname__


def version():
    """
    Return the extension version and the version of the bundled ``gws`` binary.

    CLI Example:

    .. code-block:: bash

        salt '*' gsuite.version
    """
    ret = {"extension": saltext.gsuite.__version__}
    try:
        ret["gws"] = _binary.version(opts=__opts__, pillar=__pillar__)
        ret["binary"] = _binary.resolve(opts=__opts__, pillar=__pillar__)
    except _binary.BinaryError as exc:
        ret["gws"] = None
        ret["error"] = str(exc)
    return ret


def call(service, resource, method, params=None, body=None, upload=None, subresource=None):
    """
    Invoke any ``gws`` method directly (generic escape hatch).

    ``resource`` and the optional ``subresource`` form the resource command path. For a nested
    call like ``gws gmail users messages list`` use ``resource='users'`` and
    ``subresource='messages'`` (a list of segments is also accepted for ``resource``).

    CLI Example:

    .. code-block:: bash

        salt '*' gsuite.call drive files list params='{"pageSize": 5}'
        salt '*' gsuite.call gmail users messages list subresource=messages params='{"userId": "me"}'
    """
    if isinstance(resource, (list, tuple)):
        resource_path = list(resource)
    else:
        resource_path = [resource]
    if subresource:
        if isinstance(subresource, (list, tuple)):
            resource_path.extend(subresource)
        else:
            resource_path.append(subresource)
    return _gws.call(
        __opts__,
        __pillar__,
        service,
        resource_path,
        method,
        params=params,
        body=body,
        upload=upload,
    )


def auth_test():
    """
    Validate the configured credentials by making a cheap authenticated call.

    Runs ``gws drive about get`` and returns ``{"result": True, ...}`` on success. On failure
    the credential error is returned rather than raised, so it is safe to use in checks.

    CLI Example:

    .. code-block:: bash

        salt '*' gsuite.auth_test
    """
    try:
        info = _gws.call(
            __opts__,
            __pillar__,
            "drive",
            ["about"],
            "get",
            params={"fields": "user,storageQuota"},
        )
        return {"result": True, "about": info}
    except _gws.CommandExecutionError as exc:
        return {"result": False, "error": str(exc)}
