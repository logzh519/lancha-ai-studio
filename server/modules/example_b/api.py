"""Read the events received by Example B."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from modules.example_b import service
from platforms.auth.dependencies import require

router = APIRouter()


class ReceivedItem(BaseModel):
    item_id: int
    name: str


@router.get("/events", response_model=list[ReceivedItem], dependencies=[Depends(require("example_b:event:view"))])
async def list_events():
    return [ReceivedItem(item_id=event.item_id, name=event.name) for event in service.list_received()]