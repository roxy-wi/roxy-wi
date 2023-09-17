from flask import Blueprint

bp = Blueprint('install', __name__)

from app.routes.install import routes
