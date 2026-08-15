# Comandos úteis — logs, tabelas e consultas

Guia rápido para **usar a CLI** e **validar a pipeline**: rodar os comandos, ver
logs, abrir o banco e consultar as tabelas. Cada item mostra o atalho via
**`make`** e o **comando direto no terminal** (o que o `make` executa por baixo).

> Pré-requisito: o Postgres precisa estar de pé (`make up` ou
> `docker compose up -d postgres`). As credenciais abaixo (`crypto_user` /
> `crypto`) são as do `.env.example`; ajuste se você mudou o `.env`.

---

## Como usar a CLI

A forma geral é sempre:

```
python -m app <comando> [opções]
```

### Onde rodar (dois jeitos)

| Jeito | Pré-requisito (1x) | Prefixo do comando |
|-------|--------------------|--------------------|
| Local (venv) | `make setup` | `.venv/bin/python -m app` |
| Docker | `make up` | `docker compose run --rm app` |

> O Docker é o mais fácil para usar `--database`, porque já traz Python,
> dependências e a conexão com o banco prontos. O `python -m app` é a mesma coisa
> rodando direto na sua máquina. Os exemplos abaixo usam o Docker; troque o
> prefixo se preferir o venv.

### Anatomia de um comando

```
docker compose run --rm app   download   --coin bitcoin   --date 2026-08-14   --database
└──────── prefixo ──────────┘ └comando─┘ └──────────── opções (flags) ─────────────────┘
```

- **comando**: `download`, `backfill` ou `daily`
- **flags**: começam com `--`; `--database` é um liga/desliga (sem valor)

### Os 3 comandos

```bash
# 1) download — uma moeda, uma data
docker compose run --rm app download --coin bitcoin --date 2026-08-14             # só o arquivo JSON
docker compose run --rm app download --coin bitcoin --date 2026-08-14 --database  # arquivo + Postgres
docker compose run --rm app download --coin ethereum --date yesterday --database  # 'yesterday' = ontem

# 2) backfill — uma moeda, um intervalo de datas
docker compose run --rm app backfill --coin bitcoin --start-date 2026-08-01 --end-date 2026-08-14 --database
docker compose run --rm app backfill --coin bitcoin --start-date 2026-08-01 --end-date 2026-08-14 --workers 5 --database

# 3) daily — as 3 moedas padrão (bitcoin/ethereum/cardano), uma data (feito p/ o cron)
docker compose run --rm app daily --database                     # de ontem
docker compose run --rm app daily --date 2026-08-10 --database   # de uma data específica
```

### O que você recebe (toda vez)

1. **Logs** no terminal (passo a passo `INFO`).
2. **Arquivo JSON** em `./data/<moeda>/<moeda>_<data>.json`.
3. Com `--database`: linha em `crypto_history` + MIN/MAX em `crypto_monthly_stats`.
4. A **última linha** é o resumo, ex.: `cardano 2026-08-13: price_usd=0.182... persisted=True`.

### Ajuda embutida (não precisa decorar)

```bash
docker compose run --rm app --help            # lista os 3 comandos
docker compose run --rm app backfill --help   # opções de um comando
```

### Fluxo típico do dia a dia

```bash
make up                                          # 1. sobe o banco (uma vez)
docker compose run --rm app daily --database     # 2. roda a coleta
make tables                                      # 3. confere o resultado
```

---

## 1. Logs

**Onde os logs aparecem:** a aplicação loga em **stdout** (padrão para
containers). Quando você roda um comando da CLI (`make demo`,
`docker compose run ... download ...`), os logs `INFO`/`ERROR` aparecem **ao vivo
no seu terminal**, porque esses containers são efêmeros (`--rm`). O container do
**Postgres** fica de pé e tem seu próprio log.

### Ver os logs dos containers

| Via make | Direto no terminal |
|----------|--------------------|
| `make logs` | `docker compose logs -f` |

```bash
# Todos os serviços, seguindo em tempo real (Ctrl+C para sair)
docker compose logs -f

# Só o Postgres
docker compose logs -f postgres

# Últimas 100 linhas, sem seguir
docker compose logs --tail 100 postgres
```

### Ver os logs da aplicação (CLI)

Como os containers da CLI são removidos após rodar, o jeito de "ver o log da
aplicação" é rodar o comando e ler a saída — ou **salvar em arquivo**:

```bash
# Roda e mostra os logs no terminal
docker compose run --rm app download --coin bitcoin --date yesterday --database

# Roda e salva os logs num arquivo (append), como no CRON de produção
docker compose run --rm app daily --database >> coingecko.log 2>&1

# Depois, acompanhar o arquivo
tail -f coingecko.log
```

> Rodando local (sem Docker), é a mesma ideia:
> `python -m app daily --database >> coingecko.log 2>&1`

---

## 2. Abrir o banco (psql) para fazer SELECTs

| Via make | Direto no terminal |
|----------|--------------------|
| `make db` | `docker compose exec postgres psql -U crypto_user -d crypto` |

```bash
docker compose exec postgres psql -U crypto_user -d crypto
```

Dentro do `psql`:

```sql
\dt                       -- lista as tabelas
\d crypto_history         -- descreve a estrutura (colunas, índices, constraints)
\d crypto_monthly_stats
SELECT * FROM crypto_history;
\q                        -- sair
```

---

## 3. Ver as tabelas sem entrar no psql (snapshot)

| Via make | Direto no terminal |
|----------|--------------------|
| `make tables` | os dois `psql -c` abaixo |

O flag `-c` roda um comando único e sai; `-T` desativa o pseudo-terminal (bom
para scripts):

```bash
# Tabela diária
docker compose exec -T postgres psql -U crypto_user -d crypto \
  -c "SELECT coin_id, date, price_usd FROM crypto_history ORDER BY coin_id, date;"

# Tabela agregada mensal (MIN/MAX)
docker compose exec -T postgres psql -U crypto_user -d crypto \
  -c "SELECT coin_id, year, month, min_price_usd, max_price_usd FROM crypto_monthly_stats ORDER BY coin_id, year, month;"
```

---

## 4. Consultas (SELECTs) úteis para a validação

Rode qualquer uma dentro do `psql` (`make db`) ou via `psql -c "<query>"`:

```sql
-- Contagem por moeda (provar que não há duplicidade após reprocessar)
SELECT coin_id, count(*) AS linhas, max(updated_at) AS ultimo_update
FROM crypto_history GROUP BY coin_id;

-- Ver que o raw_json guarda a resposta COMPLETA (campos que não viraram coluna)
SELECT coin_id,
       raw_json->>'name'                                        AS nome,
       raw_json->'market_data'->'current_price'->>'usd'         AS preco_usd,
       raw_json->'market_data'->'market_cap'->>'usd'            AS market_cap
FROM crypto_history WHERE coin_id = 'bitcoin';

-- Conferir o MIN/MAX mensal contra os dados diários (devem bater)
SELECT coin_id,
       min(price_usd) AS min_diario,
       max(price_usd) AS max_diario
FROM crypto_history
WHERE coin_id = 'ethereum'
GROUP BY coin_id;

-- Distinguir INSERT de UPDATE: linhas que já foram atualizadas
SELECT coin_id, date, created_at, updated_at
FROM crypto_history
WHERE updated_at > created_at;
```

---

## 5. Arquivos JSON brutos

Ficam no host em `./data/<moeda>/<moeda>_<data>.json` (volume montado no Docker):

```bash
ls -R data/                                             # lista os arquivos
cat data/bitcoin/bitcoin_2026-08-14.json | python3 -m json.tool   # JSON formatado
```

---

## Resumo — equivalência make ↔ terminal

| Objetivo | make | Terminal direto |
|----------|------|-----------------|
| Seguir logs | `make logs` | `docker compose logs -f` |
| Snapshot das tabelas | `make tables` | `docker compose exec -T postgres psql -U crypto_user -d crypto -c "SELECT ..."` |
| psql interativo | `make db` | `docker compose exec postgres psql -U crypto_user -d crypto` |
| Rodar a pipeline | `make demo` | `docker compose run --rm app download --coin bitcoin --date yesterday --database` |
| Salvar log em arquivo | — | `docker compose run --rm app daily --database >> coingecko.log 2>&1` |
