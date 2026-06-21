from pydantic import BaseModel
from typing import Optional
from enum import Enum


class DepthMode(str, Enum):
    quick = "quick"
    standard = "standard"
    deep = "deep"


class SearchSubtask(BaseModel):
    id: str
    query: str
    source_type: str
    time_period: Optional[str] = None
    domain_focus: Optional[str] = None
    priority: int
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class SearchPlannerOutput(BaseModel):
    subtasks: list[SearchSubtask]


class SearchResult(BaseModel):
    query: str
    search_result: str
    source: str
    publish_date: str
    title: str = ""


class ResearchRequest(BaseModel):
    query: str
    depth_mode: DepthMode = DepthMode.standard
    session_id: str


class SourceEntry(BaseModel):
    url: str
    title: str
    publish_date: str
