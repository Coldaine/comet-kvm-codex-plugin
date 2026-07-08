# Stateful BIOS Transition Graph & State Models

The sidecar maintains a transactional, persistent state graph in an SQLite database (at `state/bios_sidecar.db`).

## 1. Unified State Schema (`BiosState`)

Every state observation decomposes into a structured JSON parse, containing:
- `state_id`: Unique trace ID.
- `frame`: Screenshot hashes (SHA256, perceptual dHash) and capture timestamp.
- `bios`: Vendor details (MSI Click BIOS, family, board family).
- `location`: Breadcrumb trail (`["SETTINGS", "Advanced", "PCI Subsystem Settings"]`) and screen kind category.
- `selection`: Highlighted row index, label (`Re-Size BAR Support`), value (`Auto`), and bounding-box.
- `controls`: List of all other visible settings or submenus detected.
- `risk`: Dangerous keywords flagged on-screen, blocks, and policy classes.
- `actions`: Permitted keyboard actions under current context.

## 2. Graph Node & Edge Transitions

- **Nodes:** Keyed by the combination of perceptual dHash + OCR fingerprint + semantic breadcrumb hashes. This ensures cycle detection and matches volatile regions (like running temperatures/fans) correctly.
- **Edges:** Directed graph edges link nodes together, labeled with the exact keystroke transition (`Enter`, `ArrowDown`, `ArrowUp`, `Escape`) and carries before/after screenshot evidence.

## 3. Route Calculation

When navigating, the driver agent asks for targets in the capability index. The stateful sidecar calculates the shortest pathway of keystrokes (using BFS) and executes intermediate hops, asserting alignment after each keypress and aborting immediately if visual or label drift occurs.
