from flask import Blueprint

bp = Blueprint('ha', __name__)

from app.routes.ha import routes
from app.routes.ha import readiness
from app.routes.ha import maintenance
from app.routes.ha import dashboard
