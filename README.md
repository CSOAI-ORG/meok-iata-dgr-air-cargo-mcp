<!-- mcp-name: io.github.CSOAI-ORG/meok-iata-dgr-air-cargo-mcp -->
[![MCP Scorecard: 84/100](https://img.shields.io/badge/proofof.ai-84%2F100-5b21b6)](https://proofof.ai/scorecard/meok-iata-dgr-air-cargo-mcp.html)

# meok-iata-dgr-air-cargo-mcp

[![PyPI](https://img.shields.io/badge/PyPI-1.0.0-blue)](https://pypi.org/project/meok-iata-dgr-air-cargo-mcp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![MCP](https://img.shields.io/badge/MCP-1.3.0+-green)](https://modelcontextprotocol.io)

> IATA Dangerous Goods Regulations air-cargo compliance toolkit. Lithium-battery PI 965-970, Shipper's Declaration §8, acceptance checklist §9, state + operator variations. By **MEOK AI Labs**.

## Why this exists

Air freight of Dangerous Goods is governed by **ICAO Annex 18** and the **Technical Instructions (Doc 9284)**, implemented by airlines through the **IATA Dangerous Goods Regulations (DGR 66th edition, 2025)**.

This extends MEOK from road (ADR) → **air**. Forwarders + car transporters moving batteries / recalled EVs by air freight face very different rules:

- Lithium batteries are heavily restricted (PI 965-970)
- State of charge MUST be ≤ 30% for Li-ion shipped alone (UN3480) under PI 965
- Many DG are **Cargo Aircraft Only (CAO)** — banned from passenger planes
- **Shipper's Declaration** is mandatory (§8) for most DG
- Per-state + per-operator variations — FedEx, UPS, Cathay all differ
- §9 acceptance checklist at carrier handover

A single mis-declared Li-ion shipment = up to **$250,000 FAA fine** + carrier embargo + lost route. This MCP gives the callable compliance toolkit.

## Install

```bash
pip install meok-iata-dgr-air-cargo-mcp
```

## Claude Desktop config

```json
{
  "mcpServers": {
    "iata-dgr-air-cargo": {
      "command": "meok-iata-dgr-air-cargo-mcp"
    }
  }
}
```

## Tools (8)

| Tool | Use case |
|------|----------|
| `classify_air_dangerous_good` | What hazard class + UN number applies? |
| `check_lithium_battery_air_transport` | UN3480/3481/3090/3091 by Wh — PI 965-970 Section IA/IB/II. |
| `check_state_of_charge_air` | Verify Li-ion ≤30% SoC (PI 965 mandatory). |
| `generate_iata_shippers_declaration` | IATA DGR §8 paperwork ready for tender. |
| `check_passenger_vs_cargo_aircraft` | Is this CAO-only? What labels apply? |
| `validate_un_specification_packaging` | Parse + validate UN spec codes (4G/Y50/S/24/GB/...). |
| `check_country_variations` | State + operator variations on the route. |
| `prepare_iata_acceptance_check` | §9 Acceptance Checklist for cargo handling agents. |

## Pricing

- **Free** — MIT self-host
- **Starter** — £99/mo (signed attestations + email support)
- **Pro** — £299/mo (multi-station dashboards + Shipper's Dec PDF export)
- **Fleet** — £1,499/mo (forwarder-grade, audit-export, SLA)

[Subscribe Pro → £99/mo](https://buy.stripe.com/aFa7sNcgAdQS0ZT1Uc8k91t) · [Talk to Nick](mailto:nicholas@meok.ai)

## Regulatory basis

- **ICAO Annex 18** — Safe Transport of Dangerous Goods by Air
- **ICAO Doc 9284** — Technical Instructions (TI) 2025-2026 edition
- **IATA DGR 66th edition** — 1 January 2025
- **UN Model Regulations** — 23rd revised
- **49 CFR Parts 171-180** — US DOT/PHMSA
- **CAA UK CAP 1349** — Aircraft DG operator approvals
- **EASA Part-CAT.GEN.MPA.200** — Carriage of dangerous goods

## Sign your responses (production)

```bash
export MEOK_HMAC_SECRET="your-secret"
meok-iata-dgr-air-cargo-mcp
```

Every tool response returns an HMAC-SHA256 signature for audit-trail evidence.

## Companion MCPs

Part of the **MEOK Transport Compliance** stack on haulage.app:

- `meok-car-transport-uk-mcp` — DVSA + tacho + C&U (road)
- `meok-ev-recall-transport-mcp` — ADR Class 9 (road)
- `meok-iata-dgr-air-cargo-mcp` — this one (air)
- `meok-vehicle-handover-mcp` — NAMA + BVRLA + POD

## License

MIT © 2026 Nicholas Templeman / MEOK AI Labs · [haulage.app](https://haulage.app)
