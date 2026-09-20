# Knowledge Contract (اهرم ۱)

## Keys
- **Canonical knowledge key:** `workspace_id` (+ optional `revision_id`)
- **Path** is mutable metadata only (rename / move must not orphan index)

## Storage
| Store | Id-keyed | Legacy (dual-read) |
|-------|----------|--------------------|
| Graph SQLite | `.code2guide/index/ws_{id}.db` | `{path_hash}.db` |
| Qdrant / hybrid | `code2guide_ws_{id}` | `code2guide_{path_hash}` |

## Migration
On first open with `workspace_id`, legacy graph DB is **copied** to id-keyed path (legacy kept for dual-read).
New writes use id-keyed names only.

## Soft-delete
Soft-delete sets graph meta `tombstone=true` — files are **not** deleted (GC later).

## Consumers
```python
from src.knowledge.manager import get_index_manager
from src.agent.tools import Code2GuideToolbox
from src.agent.workflow import Code2GuideAgent

mgr = get_index_manager(path, workspace_id=ws_id)
tb = Code2GuideToolbox(path, workspace_id=ws_id)
agent = Code2GuideAgent(workspace_path=path, workspace_id=ws_id)
```

Do **not** use raw path as the knowledge identity.
