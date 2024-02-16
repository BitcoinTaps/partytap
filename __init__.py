import asyncio
from typing import List

from fastapi import APIRouter
from fastapi.staticfiles import StaticFiles

from lnbits.db import Database
from lnbits.helpers import template_renderer
from lnbits.tasks import catch_everything_and_restart



db = Database("ext_partytap")

partytap_ext: APIRouter = APIRouter(prefix="/partytap", tags=["partytap"])

scheduled_tasks: List[asyncio.Task] = []

partytap_static_files = [
    {
        "path": "/partytap/static",
        "app": StaticFiles(directory="lnbits/extensions/partytap/static"),
        "name": "partytap_static",
    }
]


def partytap_renderer():
    return template_renderer(["lnbits/extensions/partytap/templates"])


from .lnurl import *  # noqa: F401,F403
from .tasks import wait_for_paid_invoices
from .views import *  # noqa: F401,F403
from .views_api import *  # noqa: F401,F403


def partytap_start():
    loop = asyncio.get_event_loop()
    task = loop.create_task(catch_everything_and_restart(wait_for_paid_invoices))
    scheduled_tasks.append(task)
