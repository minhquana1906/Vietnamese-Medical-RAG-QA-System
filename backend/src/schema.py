from typing import Dict, Optional

from pydantic import BaseModel, Field


class CompleteRequest(BaseModel):
    bot_id: str = Field(
        default="medical_rag_bot",
        description="The ID of the bot to use for completion.",
    )
    user_id: str = Field(default="user_1", description="The ID of the user making the request.")
    user_message: str = Field(..., description="The message from the user.")
    is_sync_request: Optional[bool] = Field(False, description="Whether the request is synchronous or asynchronous.")
    metadata: Optional[Dict] = Field(None, description="Additional metadata for the request.")
