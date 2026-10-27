from app.modules.db.db_model import PacemakerCluster, PacemakerChange, PacemakerEvent


def up():
    PacemakerCluster._meta.database.create_tables(
        [PacemakerCluster, PacemakerChange, PacemakerEvent], safe=True
    )


def down():
    PacemakerCluster._meta.database.drop_tables(
        [PacemakerEvent, PacemakerChange, PacemakerCluster], safe=True
    )
