from models.schemas import SearchSubtask, SearchResult, DepthMode
from tools.exa_search import exa_search

_NUM_RESULTS = {
    DepthMode.quick: 3,
    DepthMode.standard: 4,
    DepthMode.deep: 5,
}


async def run_subtask(subtask: SearchSubtask, depth_mode: DepthMode) -> list[SearchResult]:
    num_results = _NUM_RESULTS[depth_mode]
    raw = await exa_search(
        query=subtask.query,
        start_date=subtask.start_date or None,
        end_date=subtask.end_date or None,
        num_results=num_results,
    )
    return [SearchResult(**r) for r in raw]
