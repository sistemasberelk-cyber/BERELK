"""
Compatibility wrapper for Jinja2Templates.TemplateResponse.

Starlette >= 0.38.0 changed the TemplateResponse signature:
  OLD: TemplateResponse(name, context_dict)  -- context must include "request"
  NEW: TemplateResponse(request, name, context)  -- request is a separate positional arg

This wrapper detects which API version is installed and adapts automatically,
so all existing call-sites using the old API keep working without modification.
"""

from fastapi.templating import Jinja2Templates
from starlette.requests import Request
from starlette.responses import Response
import inspect


class CompatTemplates(Jinja2Templates):
    """Drop-in replacement for Jinja2Templates that supports both old and new
    TemplateResponse call signatures transparently."""

    def TemplateResponse(self, *args, **kwargs) -> Response:
        # Detect the OLD call pattern: TemplateResponse("name.html", {"request": req, ...})
        if args and isinstance(args[0], str):
            name = args[0]
            context = args[1] if len(args) > 1 else kwargs.pop("context", {})

            # Extract request from context (old pattern always has it there)
            request = context.pop("request", None)

            if request is None:
                # Fallback: maybe it was in kwargs
                request = kwargs.pop("request", None)

            if request is None:
                raise ValueError("TemplateResponse requires a 'request' in context or as kwarg")

            # Check if parent's TemplateResponse accepts 'request' as first positional
            # (new Starlette API)
            sig = inspect.signature(super().TemplateResponse)
            params = list(sig.parameters.keys())

            if params and params[0] == "request":
                # NEW API: TemplateResponse(request, name, context, ...)
                return super().TemplateResponse(request=request, name=name, context=context, **kwargs)
            else:
                # OLD API: TemplateResponse(name, context, ...)
                context["request"] = request
                return super().TemplateResponse(name, context, **kwargs)
        else:
            # Already using new-style or keyword-only → pass through
            return super().TemplateResponse(*args, **kwargs)
