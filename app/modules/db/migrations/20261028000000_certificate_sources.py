from app.modules.db.db_model import CertificateSource


def up():
    CertificateSource._meta.database.create_tables([CertificateSource], safe=True)


def down():
    CertificateSource._meta.database.drop_tables([CertificateSource], safe=True)
