"""Portable fields for bounded encrypted payloads larger than MySQL TEXT."""
from peewee import TextField


class LargeTextField(TextField):
    # SQLite keeps TEXT affinity; MySQL uses its explicit large-text type.
    field_type = 'LONGTEXT'
