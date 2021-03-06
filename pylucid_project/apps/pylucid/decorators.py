# coding: utf-8

"""
    PyLucid decorators
    ~~~~~~~~~~~~~~~~~~

    :copyleft: 2009-2010 by the PyLucid team, see AUTHORS for more details.
    :license: GNU GPL v3 or above, see LICENSE for more details.
"""

import sys
import warnings
from pylucid_project.apps.pylucid.shortcuts import bad_request
try:
    from functools import wraps
except ImportError:
    from django.utils.functional import wraps  # Python 2.3, 2.4 fallback.

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.utils.translation import ugettext as _

from pylucid_project.apps.pylucid.models import LogEntry


def check_permissions(superuser_only, permissions=(), must_staff=None):
    """
    Protect a view and limit it to users witch are log in and has the permissions.
    If the user is not log in -> Redirect him to a log in view with a next_url back to the requested page.
    
    must_staff is optional: User must be staff user, if no permissions given
    
    Usage:
    --------------------------------------------------------------------------
    from pylucid_project.apps.pylucid.decorators import check_permissions
    
    @check_permissions(superuser_only=False, permissions=(u'appname.add_modelname', u'appname.change_modelname'))
    def my_view(request):
        ...
        
    @check_permissions(superuser_only=False, must_staff=True)
    def view_only_for staff_members(request):
        ...
    --------------------------------------------------------------------------
    """
    assert isinstance(superuser_only, bool)
    assert isinstance(permissions, (list, tuple))

    if must_staff is None:
        if permissions:
            must_staff = False
        else:
            must_staff = True

    assert isinstance(must_staff, bool)

    def _inner(view_function):
        @wraps(view_function)
        def _check_permissions(request, *args, **kwargs):
            user = request.user

            if not user.is_authenticated():
                msg = _("Permission denied for anonymous user. Please log in.")
                LogEntry.objects.log_action(app_label="PyLucid", action="auth error", message=msg)
                messages.error(request, msg)
                url = settings.PYLUCID.AUTH_NEXT_URL % {"path": "/", "next_url": request.path}
                return HttpResponseRedirect(url)

            def permission_denied(msg):
                LogEntry.objects.log_action(app_label="PyLucid", action="auth error", message=msg)
                raise PermissionDenied()

            if superuser_only and user.is_superuser != True:
                return permission_denied("Your are not a superuser!")

            if must_staff and user.is_staff != True:
                return permission_denied("Your are not a staff member!")

            if not user.has_perms(permissions):
                msg = "User %r has not all permissions: %r (existing permissions: %r)" % (
                    user, permissions, user.get_all_permissions()
                )
                return permission_denied(msg)

            return view_function(request, *args, **kwargs)

        # Add superuser_only and permissions attributes, so they are accessible
        # Used to build the admin menu
        _check_permissions.access_permissions = (superuser_only, permissions, must_staff)

        return _check_permissions
    return _inner


def superuser_only(view_function):
    """
    Limit view to superusers only.
    TODO: Add a log entry, if PermissionDenied raised.
    
    Usage:
    --------------------------------------------------------------------------
    from pylucid_project.apps.pylucid.decorators import superuser_only
    
    @superuser_only
    def my_view(request):
        ...
    --------------------------------------------------------------------------
    
    or in urls:
    
    --------------------------------------------------------------------------
    urlpatterns = patterns('',
        (r'^foobar/(.*)', is_staff(my_view)),
    )
    --------------------------------------------------------------------------    
    """
    @wraps(view_function)
    def _inner(request, *args, **kwargs):
        if not request.user.is_superuser:
            raise PermissionDenied
        return view_function(request, *args, **kwargs)
    return _inner


def check_request(app_label, action, must_post=False, must_ajax=False):
    assert (must_post or must_ajax), "must_post or must_ajax must be set to True!"
    def _inner(view_function):
        @wraps(view_function)
        def _wrapper(request, *args, **kwargs):
            if must_post and request.method != 'POST':
                return bad_request(app_label=app_label, action=action,
                    debug_msg="request method %r wrong, only POST allowed" % request.method
                )
            if must_ajax and request.is_ajax() != True:
                return bad_request(app_label=app_label, action=action,
                    debug_msg="request is not a ajax request"
                )
            return view_function(request, *args, **kwargs)
        return _wrapper
    return _inner


# TODO: Use this from django-tools!
def render_to(template_name=None, debug=False):
    """
    Based on the decorators from django-annoying.

    Example:
 
        @render_to('foo/template.html')
        def PyLucidPluginFoo(request):
            bar = Bar.object.all()  
            return {'bar': bar}
        
    The view can also insert the template name in the context, e.g.:

        @render_to
        def PyLucidPluginFoo(request):
            bar = Bar.object.all()  
            return {'bar': bar, 'template_name': 'foo/template.html'}

    TODO: merge render_to() and render_pylucid_response()
    """
    def renderer(function):
        @wraps(function)
        def wrapper(request, *args, **kwargs):
            context = function(request, *args, **kwargs)

            if not isinstance(context, dict):
                if debug:
                    msg = (
                        "renter_to info: %s (template: %r)"
                        " has not return a dict, has return: %r (%r)"
                    ) % (function.__name__, template_name, type(context), function.func_code)
                    messages.info(request, msg)
                return context

            template_name2 = context.pop('template_name', template_name)
            assert template_name2 != None, \
                ("Template name must be passed as render_to parameter"
                " or 'template_name' must be inserted into context!")

            response = render_to_response(template_name2, context, context_instance=RequestContext(request))

            if debug:
                messages.info(request, "render debug for %r (template: %r):" % (function.__name__, template_name2))
                messages.info(request, "local view context:", context)
                messages.info(request, "response:", response.content)

            return response
        return wrapper
    return renderer
