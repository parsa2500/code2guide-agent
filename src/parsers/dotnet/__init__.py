"""ASP.NET Core / .NET / MVC Framework backend parsers (regex heuristics, no Roslyn)."""

from src.parsers.dotnet.api_parser import DotNetApiParser, ParsedEndpoint
from src.parsers.dotnet.service_parser import DotNetServiceParser, ParsedService
from src.parsers.dotnet.entity_parser import DotNetEntityParser, ParsedEntity, ParsedField
from src.parsers.dotnet.migration_parser import DotNetMigrationParser, ParsedTable
from src.parsers.dotnet.mvc_api_parser import MvcApiParser

__all__ = [
    "DotNetApiParser",
    "ParsedEndpoint",
    "DotNetServiceParser",
    "ParsedService",
    "DotNetEntityParser",
    "ParsedEntity",
    "ParsedField",
    "DotNetMigrationParser",
    "ParsedTable",
    "MvcApiParser",
]
