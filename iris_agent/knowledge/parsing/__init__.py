"""Document parsing layer for the local RAG knowledge base."""

from iris_agent.knowledge.parsing.base import ParsingError, ParsedDocument, ParsedSection
from iris_agent.knowledge.parsing.registry import parse_document, supported_suffixes
from iris_agent.knowledge.parsing.vision import OllamaImageDescriber

__all__ = ["OllamaImageDescriber", "ParsingError", "ParsedDocument", "ParsedSection", "parse_document", "supported_suffixes"]
