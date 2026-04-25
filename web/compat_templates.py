from fastapi.templating import Jinja2Templates
from starlette.background import BackgroundTask
from typing import Any, Optional, Mapping

class CompatTemplates(Jinja2Templates):
    def TemplateResponse(self, name, context, status_code=200, headers=None, media_type=None, background=None):
        return super().TemplateResponse(name, context, status_code, headers, media_type, background)
