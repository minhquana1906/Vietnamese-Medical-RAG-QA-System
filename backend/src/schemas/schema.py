from typing import Dict, List, Optional
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

# class CompleteRequest(BaseModel):

#     bot_id: str = Field(
#         default="Meddy",
#         description="The ID of the bot to use for completion.",
#     )
#     user_id: str = Field(
#         default="user_1", description="The ID of the user making the request."
#     )
#     user_message: str = Field(..., description="The message from the user.")
#     is_sync_request: Optional[bool] = Field(
#         False, description="Whether the request is synchronous or asynchronous."
#     )
#     metadata: Optional[Dict] = Field(
#         None, description="Additional metadata for the request."
#     )


class RAGQueryRequest(BaseModel):

    user_identifier: str = Field(..., description="User identifier from authentication")
    thread_id: str = Field(..., description="Thread/conversation ID (UUID)")
    query: str = Field(..., description="User's question")
    metadata: Optional[Dict] = Field(None, description="Additional metadata")


class RAGQueryResponse(BaseModel):

    thread_id: str = Field(..., description="Thread ID")
    response: str = Field(..., description="Assistant's response")
    sources: Optional[List[Dict]] = Field(None, description="Source documents used")
    metadata: Optional[Dict] = Field(None, description="Additional response metadata")


class HealthCheckResponse(BaseModel):
    """Health check response for individual services"""

    status: str = Field(..., description="Health status (ok/error/degraded)")
    service: str = Field(..., description="Service name (api/database/cache)")
    details: Optional[Dict] = Field(None, description="Additional service details")
    message: Optional[str] = Field(None, description="Additional status information")


class SystemHealthResponse(BaseModel):

    status: str = Field(..., description="Overall system status")
    api: HealthCheckResponse = Field(..., description="API health status")
    database: HealthCheckResponse = Field(..., description="Database health status")
    cache: HealthCheckResponse = Field(..., description="Cache health status")


# Removed Model Management Schemas - now using config/models.yaml instead
