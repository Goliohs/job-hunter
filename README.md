# Job Hunter Bot

Bot de búsqueda de trabajo remoto que filtra ofertas automáticamente con LLM.

## Concepto

No es un "bot mágico que aplica a mil lugares". Es un **pipeline analítico**:

1. **Scrapea fuentes públicas** (Remotive, RemoteOK, WeWorkRemotely, HN Who's Hiring)
2. **Guarda en SQLite** (dedupe automático)
3. **Pre-filtro heurístico** (dealbreakers: onsite, senior, >2 años exp, on-call)
4. **Filtro LLM (NIM)** — puntúa 0-100 según tu perfil y reject dealbreakers
5. **Dashboard CLI** — muestra top matches para que decidas a cuál aplicar

Las únicas fuentes que usa son **APIs públicas** donde el acceso es anónimo. No toca
LinkedIn para nada (ahí no aplica el bot, solo lo mejorás manualmente tu perfil).

## Stack objetivo del bot

Por ahora configura para:
- Junior / entry-level, máx 2 años exp
- Remote worldwide
- Stack: JavaScript/React, Python, WordPress, PHP, SQL, HTML/CSS, Git
- Rechaza: onsite, senior, on-call, client-facing, security clearance

Editá `config.yaml` si necesitás ajustar.

## Uso

```bash
# 1. Configura tu API key de NIM (https://build.nvidia.com)
cp .env.example .env
# Edita .env con tu NIM_API_KEY

# 2. Scrapea y filtra (pipeline completo)
./run.sh

# 3. Solo scrapea (sin gastar LLM)
./run.sh scrape

# 4. Ver top 20 matches
./run.sh top

# 5. Stats
./run.sh stats

# 6. Loop continuo (cada 6h)
./run.sh cron
```

## Estructura

```
job-hunter/
├── config.yaml          # Tu perfil, filtros, sources
├── .env                 # Tu NIM_API_KEY (NO commitear)
├── run.sh               # Wrapper bash
├── main.py              # Entry point
├── jobs.db              # SQLite autogenerado
├── aggregator/
│   ├── remotive.py      # API JSON
│   ├── remoteok.py      # API JSON
│   ├── wwr.py           # RSS
│   └── hn.py            # HN Firebase API + Algolia
├── filter/
│   ├── nim_client.py    # Cliente NIM (OpenAI-compatible)
│   └── matcher.py       # Pre-filtro + invocación LLM
└── db/
    ├── schema.sql       # Tabla jobs + run_log
    └── store.py         # CRUD SQLite
```

## Fases

- [x] **Fase 1**: Agregador + DB + Filtro LLM → ACTUAL
- [ ] Fase 2: Dashboard web local + alertas Telegram
- [ ] Fase 3: Auto-aplicación a ATS abiertos (Lever/Greenhouse/Ashby)
- [ ] Fase 4: Generador de cover letter + CV adaptativo por oferta

## Costos

- NIM API: créditos gratis en build.nvidia.com (suficiente para stage initial)
- Sin otro costo: HTTP scraping + SQLite local

## Anti-ban

Este bot **NO** toca LinkedIn, no requiere login en nada, no usa cookies de sesión.
Todas las fuentes son endpoints públicos diseñados para ser consumidos.
