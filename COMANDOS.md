# Comandos úteis — logs, tabelas e consultas

Guia rápido para validar a pipeline: ver logs, abrir o banco e consultar as
tabelas. Cada item mostra o atalho via **`make`** e o **comando direto no
terminal** (o que o `make` executa por baixo).

> Pré-requisito: o Postgres precisa estar de pé (`make up` ou
> `docker compose up -d postgres`). As credenciais abaixo (`crypto_user` /
> `crypto`) são as do `.env.example`; ajuste se você mudou o `.env`.

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
