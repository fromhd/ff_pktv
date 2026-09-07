from .setup import *


class ModelPktvItem(ModelBase):
    P = P
    __tablename__ = "play_item"
    __table_args__ = {"mysql_collate": "utf8_general_ci"}
    __bind_key__ = P.package_name

    id = db.Column(db.Integer, primary_key=True)
    created_time = db.Column(db.DateTime)
    ch_id = db.Column(db.Integer)
    channel = db.Column(db.String)
    current = db.Column(db.String)
    url = db.Column(db.String)

    def __init__(self):
        self.created_time = datetime.now()
