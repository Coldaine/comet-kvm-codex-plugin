# R3 — Crawl Planner Is Not DFS

**Severity:** 🔴 Critical
**Filed against:** PR #12 (`feat/bios-sidecar-runtime`)
**Design section:** §12 — Crawl planner

---

## The gap

The design plan specifies a **depth-first search crawler** with:

1. A frontier queue of unexplored edges
2. Depth tracking and max-depth enforcement
3. Backtracking (Escape) when a branch is exhausted
4. Cycle detection to avoid revisiting the same screen
5. A "highest-value unexplored edge" selection strategy

The implementation in `controller/crawl.py` is a **single-step heuristic**:

```
if cursor is on a submenu AND Enter is allowed → press Enter
else if ArrowDown is allowed → press ArrowDown
else if Escape is allowed → press Escape
else → stop
```

This is not a DFS. It will:

- Press Enter into a submenu, then keep pressing ArrowDown forever on the submenu's rows
- Never backtrack to the parent menu after exhausting a submenu
- Never track which neighbor edges were explored
- Loop infinitely on screens with only one row (Enter→see same screen→Enter→see same screen→...)
- Ignore the `max_depth` parameter entirely

---

## Concrete failure scenarios

| BIOS screen structure | What the crawler does | What it should do |
|---|---|---|
| SETTINGS → Advanced → PCI Subsystem Settings (3 deep) | Presses ArrowDown on SETTINGS, hits Enter on Advanced, then keeps pressing ArrowDown on rows inside Advanced | Descend to PCI Subsystem Settings, enumerate its entries, then Escape back to Advanced, ArrowDown to next submenu, Enter, repeat |
| Setting screen with 1 row and no submenus | Presses Escape (back up) after failing ArrowDown | Should stop since no unexplored edges remain |
| A loop: Screen A → Enter → Screen B → Escape → Screen A | Presses Enter on Screen A, sees Screen B, presses Escape, sees Screen A, presses Enter again — **infinite loop** | Should detect that A→B→A is a cycle and mark A as fully explored |

---

## Required fix

Replace `BiosCrawler.execute_crawl_step()` with a proper DFS crawl loop in a new method `dfs_crawl()`:

```python
class BiosCrawler:
    def __init__(self, ...):
        self.frontier: List[CrawlEdge] = []  # (parent_node_id, action_key, depth)
        self.backtrack_stack: List[str] = []  # node_ids to backtrack through
        self.visited: Set[str] = set()
        self.depth: int = 0

    async def dfs_crawl(self, ..., max_depth=8) -> ...:
        """Full DFS crawl loop with backtracking."""
        # 1. Observe current state and get/create node
        # 2. If node not visited, enumerate all outgoing candidate actions
        # 3. Add unexplored candidates to frontier
        # 4. If frontier empty, pop backtrack_stack and Escape up
        # 5. Execute the highest-value frontier edge
        # 6. If new state matches an already-visited node → cycle detected, backtrack
        # 7. Push current node to backtrack_stack before descending
        # 8. Repeat until frontier is empty or max_depth exceeded
```

The current `bios_crawl_step` MCP tool can remain as a "manual single-step" tool for debugging, but `bios_crawl_region` must use `dfs_crawl()`.

---

## Remediation checklist

- [ ] Implement `dfs_crawl()` with frontier queue and backtrack stack
- [ ] Track `depth` and enforce `max_depth`
- [ ] Detect cycles (encountering a visited node via a non-Escape edge)
- [ ] Wire `bios_crawl_region` to `dfs_crawl()` instead of a `while` loop of `execute_crawl_step()`
- [ ] Keep `bios_crawl_step` as a debug single-step tool
- [ ] Test against a mock BIOS graph with known structure
