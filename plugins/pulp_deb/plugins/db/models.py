
import mongoengine
from pulp.server.db.model import FileContentUnit


class DEB(FileContentUnit):
    # TODO add docstring to this class

    # Unit Key Fields
    Package = mongoengine.StringField(required=True)
    Version = mongoengine.StringField(required=True)
    Architecture = mongoengine.StringField(required=True)
    MD5sum = mongoengine.StringField(required=True)

    # Other Fields
    Maintainer = mongoengine.StringField()
    Installed_Size = mongoengine.IntField()
    Depends = mongoengine.StringField()
    Size = mongoengine.IntField()
    SHA1 = mongoengine.StringField()
    SHA256 = mongoengine.StringField()
    Section = mongoengine.StringField()
    Priority = mongoengine.StringField()
    Homepage = mongoengine.StringField()
    Description = mongoengine.StringField()
    Filename = mongoengine.StringField()
    Suggests = mongoengine.StringField()
    Source = mongoengine.StringField()
    Multi_Arch = mongoengine.StringField()

    unit_key_fields = ('Package', 'Version', 'Architecture', 'MD5sum')
    _content_type_id = mongoengine.StringField(required=True, default='deb')
    unit_display_name = 'DEB'
    unit_description = 'DEB'
