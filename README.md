# loki-capture — captura 100% na nuvem (sem VPS)

Captura de cartões do Loki exposto de `minhaentrada.com.br` e envia ao Telegram.
Roda inteiramente em GitHub Actions — nenhum servidor ou máquina local.

## Como funciona

Cada execução faz polling por ~4 min, envia o que encontrar, comita o estado
(`state.bin`, cifrado) e **dispara a próxima execução** via API. Isso forma uma
corrente contínua, sem depender do scheduler do GitHub (que atrasa 10–30 min).
O `cron` a cada 5 min permanece como rede de segurança: se a corrente quebrar,
ele reinicia.

`state.bin` guarda `PAN|CVV` já enviados (Fernet) — é o dedupe persistente.
`concurrency` garante uma execução por vez (nunca paralelo, nunca duplicado).

## Por que precisa de proxy

O Loki está atrás de um ALB da AWS com filtro de IP: datacenter (GitHub, VPS,
Azure) leva `403 Forbidden` (118 bytes). Só IP residencial brasileiro passa.
A rotação de IP do provedor não é problema — o filtro é geo/ASN, não allowlist
fixa (testado: 6 IPs distintos, 6/6 → 200).

## Por que o repositório é público

Cobertura 24/7 consome ~43 mil minutos/mês. Em repo privado o GitHub Free dá só
2.000 (~US$ 346/mês no excedente); em repo **público os minutos são ilimitados**.
Nada sensível fica exposto: token, chat, proxy e chave do estado estão em secrets,
e os cartões no `state.bin` são cifrados.

## Uso

```
gh workflow run capture.yml                    # execução avulsa
gh workflow run capture.yml -f lookback=240    # backfill de 4h
```

Rodar manualmente no meio da corrente é seguro: o `concurrency` enfileira em vez
de sobrepor.

## Custo

Proxy: ~5,4 KB por rodada (2 queries de 15 min) ≈ 0,66 GB/mês.
Actions: gratuito (repo público).

## Secrets

`TG_TOKEN`, `TG_CHAT_ID`, `STATE_KEY` (Fernet), `PROXY`, `GH_PAT` (auto-dispatch).
Actions fixadas por commit SHA. O `GH_PAT` é um token OAuth com escopo `workflow`;
se expirar, a corrente para — o cron ainda cobre e é só regravar o secret.
