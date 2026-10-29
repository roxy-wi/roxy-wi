from flask import Blueprint

bp = Blueprint('passkeys', __name__)

from app.routes.passkeys import routes
