from app.modules.db.db_model import (User, UserSecurity, AuthenticationChallenge, RecoveryCode,
                                     AuthenticationPolicy, AuthenticationEvent)


def up():
    database = User._meta.database
    database.create_tables([UserSecurity, AuthenticationChallenge, RecoveryCode,
                            AuthenticationPolicy, AuthenticationEvent], safe=True)
    from app.modules.authentication.security import initialize_baseline
    initialize_baseline()


def down():
    raise RuntimeError('Local authentication rollback requires an explicit account recovery plan')
