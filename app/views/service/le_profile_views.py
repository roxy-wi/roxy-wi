from flask import jsonify
from flask.views import MethodView
from flask_jwt_extended import jwt_required
from flask_pydantic import validate

from app.middleware import get_user_params, page_for_admin, check_group
from app.modules.db.db_model import LetsEncryptDnsProfile
from app.modules.roxywi.class_models import GroupQuery, LetsEncryptDnsProfileRequest
from app.modules.service.le import le_profiles
from app.views.service.lets_encrypt_views import identity, le_error


class LetsEncryptDnsProfilesView(MethodView):
    decorators = [jwt_required(), get_user_params(), page_for_admin(level=3), check_group()]

    @validate(query=GroupQuery)
    def get(self, query: GroupQuery):
        try:
            group_id, _ = identity(query)
            return jsonify([le_profiles.public(row) for row in LetsEncryptDnsProfile.select().where(
                LetsEncryptDnsProfile.group_id == int(group_id)).order_by(LetsEncryptDnsProfile.name)])
        except Exception as error:
            return le_error(error, 'Cannot list DNS profiles')

    @validate(body=LetsEncryptDnsProfileRequest, query=GroupQuery)
    def post(self, body: LetsEncryptDnsProfileRequest, query: GroupQuery):
        try:
            return le_profiles.save(body.model_dump(), identity(query)[0]), 201
        except Exception as error:
            return le_error(error, 'Cannot create DNS profile')


class LetsEncryptDnsProfileView(MethodView):
    decorators = LetsEncryptDnsProfilesView.decorators

    @validate(body=LetsEncryptDnsProfileRequest, query=GroupQuery)
    def put(self, profile_id: int, body: LetsEncryptDnsProfileRequest, query: GroupQuery):
        try:
            return le_profiles.save(body.model_dump(), identity(query)[0], profile_id)
        except Exception as error:
            return le_error(error, 'Cannot update DNS profile')

    @validate(query=GroupQuery)
    def delete(self, profile_id: int, query: GroupQuery):
        try:
            le_profiles.delete(profile_id, identity(query)[0])
            return '', 204
        except Exception as error:
            return le_error(error, 'Cannot delete DNS profile')
