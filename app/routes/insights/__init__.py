from flask import Blueprint

bp=Blueprint('insights',__name__)

from app.routes.insights import routes
