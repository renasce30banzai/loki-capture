# loki-capture — fallback na nuvem

Captura de cartões do Loki exposto de `minhaentrada.com.br`.

## Papéis

| Ambientes | Papel | Egress |
|---|---|---|
| Mac (launchd `com.teampurple.loki`) | **primário** | IP residencial BR direto |
| GitHub Actions (este repo) | fallback manual | proxy residencial BR (IPPeak) |

**Não rode os dois ao mesmo tempo** — o dedupe do Mac (`~/loki-realtime-cards.txt`) e o
`state.bin` daqui são listas independentes, então cartão novo sairia duplicado.

## Uso do fallback

```
gh workflow run capture.yml
```

## Por que precisa de proxy

O Loki está atrás de ALB da AWS com filtro de IP: datacenter (GitHub, VPS) recebe
`403 Forbidden` (118 bytes). Só IP residencial brasileiro passa. A rotação do IPPeak
não é problema — o filtro é geo/ASN, não allowlist fixa (testado: 6 IPs distintos, 6/6 → 200).

## Consumo

~5,4 KB por rodada (2 queries de 15 min). Proxy só é consumido aqui; o Mac não usa.
Evite deixar o cron ligado sem necessidade.

## Secrets

`TG_TOKEN`, `TG_CHAT_ID`, `STATE_KEY` (Fernet do `state.bin`), `PROXY`.
Actions pinadas por commit SHA.
