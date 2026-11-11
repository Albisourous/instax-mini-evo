# Graph Report - instax-mini-evo  (2026-11-10)

## Corpus Check
- Corpus is ~7,312 words - fits in a single context window. You may not need a graph.

## Summary
- 97 nodes · 180 edges · 10 communities (6 shown, 4 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 10 edges (avg confidence: 0.86)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- FAT16 Filesystem Tools
- Firmware RE Concepts
- Carve & Repack Pipeline
- CLI & Mod Application
- SUNP Container Parser
- BLE Probe Tool
- Layout Inspector
- FujiFile BLE Protocol
- Snappy Codec
- SUNP Format Docs

## God Nodes (most connected - your core abstractions)
1. `FatImage` - 14 edges
2. `main()` - 7 edges
3. `carve()` - 6 edges
4. `u32()` - 6 edges
5. `parts()` - 6 edges
6. `SUNP BURN FILE container format` - 6 edges
7. `FatError` - 5 edges
8. `u16()` - 5 edges
9. `main()` - 5 edges
10. `SunpError` - 5 edges

## Surprising Connections (you probably didn't know these)
- `stock FPUPDATE.DAT firmware v1.09` --semantically_similar_to--> `FPUPDATE.DAT v1.09 firmware image`  [INFERRED] [semantically similar]
  README.md → docs/research.md
- `out/FPUPDATE_MOD.DAT build output` --references--> `FPUPDATE.DAT v1.09 firmware image`  [EXTRACTED]
  README.md → docs/research.md
- `instax-evo build pipeline` --implements--> `SUNP BURN FILE container format`  [EXTRACTED]
  README.md → docs/research.md
- `Signature trailer (stale after mods)` --rationale_for--> `Brick risk warning`  [EXTRACTED]
  docs/research.md → README.md
- `instax-evo build pipeline` --references--> `printer-boot-skip mod`  [EXTRACTED]
  README.md → docs/research.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **instax-evo build pipeline (download, carve, mod, repack)** — readme_instax_evo_cli, readme_stock_firmware_v109, tools_carve, readme_mods_py, tools_repack, readme_fpupdate_mod_dat [EXTRACTED 0.90]
- **Film effect system** — docs_research_iq_filmeffect, docs_research_param_setters_p1_p8, docs_research_p5_tint_block, docs_research_dial_handlers, docs_research_film_wkw [EXTRACTED 1.00]
- **BLE photo transfer path** — docs_research_fujifile_protocol, docs_research_gatt_dispatcher, docs_research_upload_pic_cmds, docs_research_ble_pairing [EXTRACTED 1.00]

## Communities (10 total, 4 thin omitted)

### Community 0 - "FAT16 Filesystem Tools"
Cohesion: 0.21
Nodes (6): main(), Entry, FatError, FatImage, u16(), u32()

### Community 1 - "Firmware RE Concepts"
Cohesion: 0.13
Nodes (17): Dial index wrap handlers (+0x18/+0x19), FAT16 A: and B: partitions, film-wkw mod (Wong Kar-wai look), HDR1 partition table, HDR2 XOR-obfuscated entries, IQ_FilmEffectModeSet dispatcher, P5 tint block / ISP params 0x2a003-6, P1-P8 param-class setters (+9 more)

### Community 2 - "Carve & Repack Pipeline"
Cohesion: 0.24
Nodes (10): FPUPDATE.DAT v1.09 firmware image, out/FPUPDATE_MOD.DAT build output, instax-evo one-command entry point, tools/mods.py mod table, stock FPUPDATE.DAT firmware v1.09, carve(), main(), main() (+2 more)

### Community 4 - "SUNP Container Parser"
Cohesion: 0.53
Nodes (7): bpb_info(), fat_size(), parse_header(), parts(), SunpError, u16(), u32()

### Community 6 - "Layout Inspector"
Cohesion: 0.70
Nodes (4): hdr_kind(), main(), scan(), u32()

### Community 7 - "FujiFile BLE Protocol"
Cohesion: 0.50
Nodes (4): BLE numeric-comparison pairing, FujiFile BLE protocol, App-command dispatcher + jump tables, UPLOAD_PIC command family

## Knowledge Gaps
- **12 isolated node(s):** `tools/sunp.py SUNP parser/repack`, `tools/mods.py mod table`, `HDR1 partition table`, `HDR2 XOR-obfuscated entries`, `ThreadX RTOS on MIPS32 4Kx` (+7 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 24 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **4 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `main()` connect `FAT16 Filesystem Tools` to `Carve & Repack Pipeline`, `CLI & Mod Application`?**
  _High betweenness centrality (0.065) - this node is a cross-community bridge._
- **Are the 3 inferred relationships involving `main()` (e.g. with `.listdir()` and `.read()`) actually correct?**
  _`main()` has 3 INFERRED edges - model-reasoned connections that need verification._
- **What connects `tools/sunp.py SUNP parser/repack`, `tools/mods.py mod table`, `HDR1 partition table` to the rest of the system?**
  _12 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Firmware RE Concepts` be split into smaller, more focused modules?**
  _Cohesion score 0.1323529411764706 - nodes in this community are weakly interconnected._