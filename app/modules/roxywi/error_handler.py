"""
Error handling module for Roxy-WI.

This module provides a unified way to handle errors across the application.
It includes functions for handling exceptions, logging errors, and returning
appropriate HTTP responses.
"""
from typing import Any, Dict, Tuple

from flask import current_app, jsonify, request, g, redirect, url_for
from werkzeug.exceptions import HTTPException
from flask_pydantic.exceptions import ValidationError

from app.modules.roxywi.class_models import ErrorResponse
from app.modules.roxywi.exception import (
    RoxywiResourceNotFound,
    RoxywiGroupMismatch,
    RoxywiGroupNotFound,
    RoxywiPermissionError,
    RoxywiConflictError,
    RoxywiValidationError,
    RoxywiInputError,
    RoxywiCheckLimits
)
import app.modules.roxywi.common as roxywi_common
from app.modules.roxywi import logger

# Map exception types to HTTP status codes
ERROR_CODE_MAPPING = {
    RoxywiResourceNotFound: 404,
    RoxywiGroupNotFound: 404,
    RoxywiGroupMismatch: 404,
    RoxywiPermissionError: 403,
    RoxywiConflictError: 409,
    RoxywiValidationError: 400,
    RoxywiCheckLimits: 402,
    KeyError: 400,
    ValueError: 400,
    Exception: 500
}

# Map exception types to error messages
ERROR_MESSAGE_MAPPING = {
    RoxywiResourceNotFound: "Resource not found",
    RoxywiGroupNotFound: "Group not found",
    RoxywiGroupMismatch: "Resource not found in group",
    RoxywiPermissionError: "You do not have permission to access this resource",
    RoxywiConflictError: "Conflict with existing resource",
    RoxywiValidationError: "Validation error",
    RoxywiCheckLimits: "You have reached your plan limits",
    KeyError: "Missing required field",
    ValueError: "Invalid value provided",
    Exception: "Internal server error",
}


def safe_error_message(exception: Exception) -> str:
    """Expose deliberate input errors, never the text of an unexpected failure."""
    if isinstance(exception, RoxywiInputError):
        return exception.public_message
    # Exception messages/tracebacks can contain credentials, SQL and file
    # contents. Record the failure without copying those into the log journal.
    logger.error('Request operation failed', error_type=type(exception).__name__)
    for exception_type, message in ERROR_MESSAGE_MAPPING.items():
        if isinstance(exception, exception_type):
            return message
    return 'Internal server error'


def _is_json_request() -> bool:
    """Keep API, health checks and background requests machine-readable."""
    return (
        request.path in {'/api', '/health'}
        or request.path.startswith(('/api/', '/health/'))
        or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or request.headers.get('Sec-Fetch-Mode') in {'cors', 'same-origin', 'no-cors'}
        or request.is_json
        or request.accept_mimetypes.best == 'application/json'
    )


def _wants_html_response() -> bool:
    accepts = request.accept_mimetypes
    return not _is_json_request() and accepts['text/html'] > 0 and (
        accepts.best == 'text/html' or accepts['text/html'] > accepts['application/json']
    )


def _error_page(status_code, message=None, language=None):
    languages = current_app.jinja_env.get_template('languages/languages.html').module.languages
    language = language or roxywi_common.get_user_lang_for_flask()
    if language not in languages:
        language = 'en'
    # Error rendering must work even when the database or a context processor
    # failed. This standalone template needs no user, subscription or menu queries.
    return current_app.jinja_env.get_template('error.html').render(
        status_code=status_code, message=message, lang=language,
    )


def error_response(error, status_code, *, http_error=None, public_message=None, language=None):
    """Render navigation errors; preserve the JSON contract and HTTP headers."""
    if _wants_html_response():
        response = current_app.response_class(
            _error_page(status_code, public_message, language), mimetype='text/html',
        )
    else:
        response = jsonify(ErrorResponse(error=error).model_dump(mode='json'))
    if http_error is not None:
        # Retain Allow, Retry-After and WWW-Authenticate from HTTPException.
        for name, value in http_error.get_response().headers:
            if name.lower() not in {'content-type', 'content-length'}:
                response.headers.add(name, value)
    response.status_code = status_code
    response.headers['Cache-Control'] = 'no-store'
    response.vary.update(('Accept', 'X-Requested-With', 'Sec-Fetch-Mode'))
    return response


def log_error(exception: Exception, server_ip: str = "Roxy-WI server", 
              additional_info: str = "", keep_history: bool = False, 
              service: str = None) -> None:
    """
    Log an error with detailed information.

    Args:
        exception: The exception that was raised
        server_ip: The IP of the server where the error occurred
        additional_info: Additional information to include in the log
        keep_history: Whether to keep the error in the action history
        service: The service where the error occurred
    """
    error_message = str(exception)
    if additional_info:
        error_message = f"{additional_info}: {error_message}"

    # Log the error with structured context
    logger.exception(
        error_message,
        exc=exception,
        server_ip=server_ip,
        service=service
    )

    # Keep history if requested
    if keep_history and service:
        try:
            # Get user information if available
            user_id = None
            user_ip = request.remote_addr if request else 'unknown'

            if hasattr(g, 'user'):
                user_id = getattr(g.user, 'user_id', None)

            if user_id:
                roxywi_common.keep_action_history(service, error_message, server_ip, user_id, user_ip)
        except Exception as e:
            logger.error(f"Failed to keep error history: {e}", server_ip=server_ip)


def handle_exception(exception: Exception, server_ip: str = "Roxy-WI server", 
                     additional_info: str = "", keep_history: bool = False, 
                     service: str = None) -> Tuple[Dict[str, Any], int]:
    """
    Handle an exception and return an appropriate HTTP response.

    Args:
        exception: The exception that was raised
        server_ip: The IP of the server where the error occurred
        additional_info: Additional information to include in the response
        keep_history: Whether to keep the error in the action history
        service: The service where the error occurred

    Returns:
        A tuple containing the error response and HTTP status code
    """
    # Log the error
    log_error(exception, server_ip, additional_info, keep_history, service)

    # Determine the exception type and get the appropriate status code and message
    for exception_type, status_code in ERROR_CODE_MAPPING.items():
        if isinstance(exception, exception_type):
            message = ERROR_MESSAGE_MAPPING[exception_type]
            if additional_info:
                message = f"{additional_info}: {message}"

            # Create the error response
            error_response = ErrorResponse(error=message).model_dump(mode='json')
            return error_response, status_code

    # If we get here, we don't have a specific handler for this exception type
    error_response = ErrorResponse(error='Internal server error').model_dump(mode='json')
    return error_response, 500


def register_error_handlers(app):
    """
    Register error handlers for the Flask application.

    Args:
        app: The Flask application
    """
    @app.after_request
    def render_navigation_error(response):
        # Some routes and JWT callbacks return JSON directly instead of raising.
        # Only replace those bodies for an explicit HTML navigation request.
        if 400 <= response.status_code < 600 and response.is_json and _wants_html_response():
            response.set_data(_error_page(response.status_code))
            response.mimetype = 'text/html'
            response.headers['Cache-Control'] = 'no-store'
            response.vary.update(('Accept', 'X-Requested-With', 'Sec-Fetch-Mode'))
        return response

    @app.errorhandler(HTTPException)
    def handle_http_error(e):
        if e.code is None:
            return e
        messages = {400: 'Bad request', 415: 'Unsupported Media Type', 429: 'Too many requests'}
        return error_response(messages.get(e.code, str(e)), e.code, http_error=e)

    @app.errorhandler(Exception)
    def handle_exception_error(e):
        """Handle all unhandled exceptions."""
        payload, status_code = handle_exception(e)
        return error_response(payload['error'], status_code)

    # Register handlers for specific HTTP errors
    @app.errorhandler(ValidationError)
    def handle_pydantic_validation_errors(e):
        """Handle validation errors from pydantic."""
        errors = []
        if e.body_params:
            req_type = e.body_params
        elif e.form_params:
            req_type = e.form_params
        elif e.path_params:
            req_type = e.path_params
        else:
            req_type = e.query_params
        for er in req_type:
            if len(er["loc"]) > 0:
                errors.append(f'{er["loc"][0]}: {er["msg"]}')
            else:
                errors.append(er["msg"])
        return error_response(errors, 400)

    @app.errorhandler(401)
    def unauthorized(e):
        """Handle 401 Unauthorized errors."""
        if _is_json_request():
            return error_response(str(e), 401, http_error=e)
        return redirect(url_for('login_page', next=request.full_path))
