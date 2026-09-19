"""ASP.NET Core / .NET backend parsers (regex heuristics, no Roslyn)."""

from src.parsers.dotnet.api_parser import DotNetApiParser, ParsedEndpoint
from src.parsers.dotnet.service_parser import DotNetServiceParser, ParsedService
from src.parsers.dotnet.entity_parser import DotNetEntityParser, ParsedEntity, ParsedField
from src.parsers.dotnet.migration_parser import DotNetMigrationParser, ParsedTable

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
]
