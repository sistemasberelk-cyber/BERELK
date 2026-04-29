from fastapi.templating import Jinja2Templates
from starlette.background import BackgroundTask
from typing import Any, Optional, Mapping

class CompatTemplates(Jinja2Templates):
    def TemplateResponse(self, name, context, status_code=200, headers=None, media_type=None, background=None):
        try:
            return super().TemplateResponse(
                request=context.get("request"),
                name=name,
                context=context,
                status_code=status_code,
                headers=headers,
                media_type=media_type,
                background=background
            )
        except TypeError:
            return super().TemplateResponse(
                name=name,
                context=context,
                status_code=status_code,
                headers=headers,
                media_type=media_type,
                background=background
            )
