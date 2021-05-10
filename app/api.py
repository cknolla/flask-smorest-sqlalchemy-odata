"""Flask-Smorest API."""
from flask_smorest import Api, Page

api = Api()


class CursorPage(Page):
    @property
    def item_count(self):
        return self.collection.count()
