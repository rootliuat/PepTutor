"""Router package marker.

Keep package import side-effect free so lightweight router modules can be tested
without triggering full API initialization.
"""

__all__ = ["document_router", "query_router", "graph_router", "OllamaAPI"]
