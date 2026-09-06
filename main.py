# ============================================================
# WHALE HUNTER v8.1 - MONITOR COMPLETO
# ============================================================
import os
import time
import threading
import requests
import telebot
from flask import Flask, request
from collections import defaultdict, deque
import json

# ============================================================
# CONFIGURAÇÃO
# ============================================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
app = Flask(__name__)

# ============================================================
# SMART MONEY WALLETS (SUBSTITUA PELAS SUAS)
# ============================================================
SMART_WALLETS = {
    "2HpvvY7TcbSdr8uNrDBUyEvbD9mcjg4ssmWQFcQcwJap": "🐋 SM#1 — ALFA",
    "7nwHPVnDEz779Rjsy8Rh9dzFmc3qBtCSs678sZoPnfgk": "🐋 SM#2 — BRAVO",
    "HXYUZorbAwEWcdgd6DwLgy5cc3zXYjsc3WbV4kMjfA6F": "🐋 SM#3 — CHARLIE",
    "MRiYA4oN3158fCV8evhuCofrDzbHyYvYnGZUDJvoCsa": "🐋 SM#4 — DELTA",
    "EvxbPV3uwE2e4cKkGXRrLJKbXcJmRdnWFqiVAm3rtK8F": "🐋 SM#5 — ECHO",
    "HZXdwRRw27kfpYtTqc7bMfrRgK3LSUaiKDFtqoEihik8": "🐋 SM#6 — FOXTROT",
}

WALLET_ADDRESSES = list(SMART_WALLETS.keys())

# ============================================================
# FILTROS
# ============================================================
FILTERS = {
    "min_liquidity": 15000,
    "min_volume_5m": 10000,
    "min_market_cap": 50000,
    "min_holders": 20,
    "min_buy_sell_ratio": 1.2,
    "max_price_change_1h": 100,
    "min_sm_buys": 3,
    "sm_accumulation_window": 600,
    "min_sm_buy_usd": 50,
    "min_sm_avg_buy_usd": 30,
    "score_minimum": 65,
    "score_elite": 80,
    "cooldown_seconds": 1800,
}

# ============================================================
# ESTADO GLOBAL
# ============================================================
processed_key = {}
PROCESSED_TTL = 600
token_history = defaultdict(lambda: deque(maxlen=20))
sm_buy_history = defaultdict(lambda: defaultdict(list))
token_cooldown = {}

def safe_float(value, default=0.0):
    try:
        return float(value or 0)
    except:
        return default

def safe_int(value, default=0):
    try:
        return int(value or 0)
    except:
        return default

def get_wallet_name(address):
    return SMART_WALLETS.get(address, f"🔴 {address[:8]}...")

def now():
    return time.time()

# ============================================================
# DEDUPLICAÇÃO
# ============================================================
def is_processed(signature, wallet, mint):
    key = f"{signature}:{wallet}:{mint}"
    if key in processed_key:
        return True
    processed_key[key] = now()
    return False

def cleanup_processed():
    cutoff = now() - PROCESSED_TTL
    for key in list(processed_key.keys()):
        if processed_key[key] < cutoff:
            del processed_key[key]

# ============================================================
# DADOS DO TOKEN
# ============================================================
def get_token_data(token_address):
    try:
        response = requests.get(
            f"https://api.dexscreener.com/latest/dex/tokens/{token_address}",
            timeout=7
        )
        if response.status_code != 200:
            return None
        data = response.json()
        pairs = data.get("pairs", [])
        if not pairs:
            return None
        
        pairs.sort(key=lambda p: safe_float((p.get("liquidity") or {}).get("usd")), reverse=True)
        p = pairs[0]
        base_token = p.get("baseToken") or {}
        txns = p.get("txns") or {}
        volume = p.get("volume") or {}
        price_change = p.get("priceChange") or {}
        liquidity = p.get("liquidity") or {}
        m5 = txns.get("m5") or {}
        
        return {
            "symbol": base_token.get("symbol", "???"),
            "price": safe_float(p.get("priceUsd")),
            "liquidity": safe_float(liquidity.get("usd")),
            "volume_5m": safe_float(volume.get("m5")),
            "volume_1h": safe_float(volume.get("h1")),
            "volume_24h": safe_float(volume.get("h24")),
            "price_change_5m": safe_float(price_change.get("m5")),
            "price_change_1h": safe_float(price_change.get("h1")),
            "price_change_24h": safe_float(price_change.get("h24")),
            "buys_5m": safe_int(m5.get("buys")),
            "sells_5m": safe_int(m5.get("sells")),
            "market_cap": safe_float(p.get("fdv")),
            "holders": safe_int((p.get("holders") or {}).get("count")),
            "age_min": ((time.time()*1000 - (p.get("pairCreatedAt") or time.time()*1000)) / 60000),
        }
    except Exception as e:
        print(f"[DEX] Erro: {e}")
        return None

# ============================================================
# ANÁLISE DO TOKEN
# ============================================================
def analyze_token(token_data):
    if not token_data:
        return "🔴 SEM DADOS", 0, ["Não foi possível obter dados do token"]
    
    score = 0
    motivos = []
    
    liquidity = safe_float(token_data.get("liquidity"))
    if liquidity >= 100000:
        score += 20
        motivos.append(f"💧 Liquidez alta (${liquidity:,.0f})")
    elif liquidity >= 50000:
        score += 15
        motivos.append(f"💧 Liquidez boa (${liquidity:,.0f})")
    elif liquidity >= 20000:
        score += 10
        motivos.append(f"💧 Liquidez média (${liquidity:,.0f})")
    elif liquidity >= 10000:
        score += 5
        motivos.append(f"💧 Liquidez baixa (${liquidity:,.0f})")
    else:
        motivos.append(f"💧 Liquidez muito baixa (${liquidity:,.0f})")
    
    volume_5m = safe_float(token_data.get("volume_5m"))
    if volume_5m >= 100000:
        score += 20
        motivos.append(f"📊 Volume 5m muito alto (${volume_5m:,.0f})")
    elif volume_5m >= 50000:
        score += 15
        motivos.append(f"📊 Volume 5m alto (${volume_5m:,.0f})")
    elif volume_5m >= 20000:
        score += 10
        motivos.append(f"📊 Volume 5m médio (${volume_5m:,.0f})")
    elif volume_5m >= 10000:
        score += 5
        motivos.append(f"📊 Volume 5m baixo (${volume_5m:,.0f})")
    else:
        motivos.append(f"📊 Volume 5m muito baixo (${volume_5m:,.0f})")
    
    market_cap = safe_float(token_data.get("market_cap"))
    if 1000000 <= market_cap <= 50000000:
        score += 15
        motivos.append(f"🏪 MC ideal (${market_cap:,.0f})")
    elif 500000 <= market_cap < 1000000:
        score += 10
        motivos.append(f"🏪 MC bom (${market_cap:,.0f})")
    elif 100000 <= market_cap < 500000:
        score += 5
        motivos.append(f"🏪 MC pequeno (${market_cap:,.0f})")
    else:
        motivos.append(f"🏪 MC fora da faixa (${market_cap:,.0f})")
    
    holders = safe_int(token_data.get("holders"))
    if holders >= 500:
        score += 10
        motivos.append(f"👥 Muitos holders ({holders})")
    elif holders >= 200:
        score += 7
        motivos.append(f"👥 Bons holders ({holders})")
    elif holders >= 100:
        score += 4
        motivos.append(f"👥 Holders ok ({holders})")
    else:
        motivos.append(f"👥 Poucos holders ({holders})")
    
    buys = safe_int(token_data.get("buys_5m"))
    sells = safe_int(token_data.get("sells_5m"))
    if sells > 0:
        ratio = buys / sells
        if ratio >= 2.0:
            score += 15
            motivos.append(f"⚖️ Ratio excelente ({ratio:.2f})")
        elif ratio >= 1.5:
            score += 10
            motivos.append(f"⚖️ Ratio bom ({ratio:.2f})")
        elif ratio >= 1.0:
            score += 5
            motivos.append(f"⚖️ Ratio ok ({ratio:.2f})")
        else:
            motivos.append(f"⚖️ Ratio ruim ({ratio:.2f})")
    else:
        if buys > 0:
            score += 10
            motivos.append(f"⚖️ Sem vendas (apenas compras)")
    
    price_change = safe_float(token_data.get("price_change_1h"))
    if 2 <= price_change <= 30:
        score += 10
        motivos.append(f"📈 Crescimento saudável (+{price_change:.1f}%)")
    elif 30 < price_change <= 60:
        score += 5
        motivos.append(f"📈 Crescimento forte (+{price_change:.1f}%)")
    elif 60 < price_change <= 100:
        score += 2
        motivos.append(f"📈 Crescimento acelerado (+{price_change:.1f}%)")
    elif price_change > 100:
        motivos.append(f"🚨 Pump extremo (+{price_change:.1f}%)")
    else:
        motivos.append(f"📈 Estável ({price_change:+.1f}%)")
    
    if score >= 70:
        return "🟢 PROMISSOR ✅", score, motivos
    elif score >= 50:
        return "🟡 INTERESSANTE ⚠️", score, motivos
    else:
        return "🔴 LIXO 🚫", score, motivos

# ============================================================
# DETECTOR DE ACUMULAÇÃO
# ============================================================
def detect_accumulation(wallet, token_address, usd_value):
    now_time = now()
    
    if usd_value < FILTERS["min_sm_buy_usd"]:
        return {"confirmed": False, "count": 0, "avg_buy": 0, "reason": "MICRO BUY"}
    
    wallet_history = sm_buy_history[token_address][wallet]
    wallet_history.append({"time": now_time, "usd_value": usd_value})
    
    cutoff = now_time - FILTERS["sm_accumulation_window"]
    sm_buy_history[token_address][wallet] = [b for b in wallet_history if b["time"] >= cutoff]
    
    buys = sm_buy_history[token_address][wallet]
    count = len(buys)
    total = sum(b["usd_value"] for b in buys)
    avg_buy = total / count if count > 0 else 0
    
    if count >= FILTERS["min_sm_buys"] and avg_buy >= FILTERS["min_sm_avg_buy_usd"]:
        elapsed = buys[-1]["time"] - buys[0]["time"]
        confirmed = elapsed <= FILTERS["sm_accumulation_window"]
        return {"confirmed": confirmed, "count": count, "avg_buy": avg_buy, "total": total, "elapsed": elapsed}
    
    return {"confirmed": False, "count": count, "avg_buy": avg_buy, "total": total, "progress": f"{count}/{FILTERS['min_sm_buys']}"}

# ============================================================
def detect_convergence(token_address):
    buyers = []
    cutoff = now() - FILTERS["sm_accumulation_window"]
    for wallet in WALLET_ADDRESSES:
        history = sm_buy_history[token_address].get(wallet, [])
        recent = [b for b in history if b["time"] >= cutoff]
        if len(recent) >= 1:
            buyers.append(wallet)
    return {"buyers": buyers, "count": len(buyers)}

# ============================================================
# PROCESSAR TRANSAÇÃO
# ============================================================
def process_transaction(event):
    try:
        cleanup_processed()
        
        fee_payer = event.get("feePayer")
        if fee_payer not in WALLET_ADDRESSES:
            return
        
        tx_type = event.get("type")
        if tx_type not in ["SWAP", "TRANSFER"]:
            return
        
        signature = event.get("signature", "")
        if not signature:
            return
        
        token_transfers = event.get("tokenTransfers", [])
        if not token_transfers:
            return
        
        token_address = None
        token_amount = 0
        is_buy = False
        
        for transfer in token_transfers:
            mint = transfer.get("mint")
            if mint == "So11111111111111111111111111111111111111112":
                if transfer.get("toUserAccount") == fee_payer:
                    is_buy = False
                else:
                    is_buy = True
            else:
                token_address = mint
                token_amount = safe_float(transfer.get("tokenAmount"))
        
        if not token_address or token_amount <= 0:
            return
        
        if is_processed(signature, fee_payer, token_address):
            return
        
        token_data = get_token_data(token_address)
        if not token_data:
            return
        
        price = safe_float(token_data.get("price"))
        usd_value = token_amount * price if price > 0 else 0
        wallet_name = get_wallet_name(fee_payer)
        symbol = token_data.get("symbol", "???")
        
        if not is_buy:
            print(f"[SELL] {wallet_name} | ${symbol} | ${usd_value:.2f}")
            return
        
        if usd_value < FILTERS["min_sm_buy_usd"]:
            print(f"[MICRO BUY] {symbol} ${usd_value:.2f}")
            return
        
        print(f"[BUY] {wallet_name} | ${symbol} | ${usd_value:.2f}")
        
        accumulation = detect_accumulation(fee_payer, token_address, usd_value)
        if not accumulation["confirmed"]:
            print(f"[ACUMULAÇÃO] {wallet_name} | ${symbol} | {accumulation.get('progress', '0/3')}")
            return
        
        convergence = detect_convergence(token_address)
        
        if token_address in token_cooldown:
            if now() - token_cooldown[token_address] < FILTERS["cooldown_seconds"]:
                print(f"[COOLDOWN] ${symbol}")
                return
        
        status, score, motivos = analyze_token(token_data)
        if score < FILTERS["score_minimum"]:
            print(f"[SCORE] ${symbol} | {score}/100")
            return
        
        token_cooldown[token_address] = now()
        
        if score >= FILTERS["score_elite"]:
            level = "🏆 ELITE ENTRY"
            urgency = "🚨"
        else:
            level = "🟢 BOA OPORTUNIDADE"
            urgency = "⚡"
        
        motivos_str = "\n".join([f"• {m}" for m in motivos[:5]])
        accum_info = f"""
🐋 *ACUMULAÇÃO CONFIRMADA!*
• {accumulation['count']} compras do mesmo SM
• Média: ${accumulation['avg_buy']:,.2f}
• Total: ${accumulation['total']:,.2f}
• Janela: {accumulation['elapsed']/60:.1f} min"""

        converg_info = f"\n🐋 *CONVERGÊNCIA!* {convergence['count']} carteiras comprando" if convergence["count"] > 1 else ""
        
        message = f"""
{urgency} *{level}*

👤 *{wallet_name}*
🟢 *ACUMULAÇÃO CONFIRMADA*

💎 *${symbol}*
📄 `{token_address[:8]}...{token_address[-8:]}`

━━━━━━━━━━━━━━━━━━

📊 *ANÁLISE DO TOKEN*

⭐ Score: `{score}/100`
{status}

{motivos_str}

━━━━━━━━━━━━━━━━━━

{accum_info}
{converg_info}

━━━━━━━━━━━━━━━━━━

📈 Variação 1h: `{safe_float(token_data.get('price_change_1h')):+.1f}%`
💧 Liquidez: `${safe_float(token_data.get('liquidity')):,.0f}`
📊 Volume 5m: `${safe_float(token_data.get('volume_5m')):,.0f}`
🏪 Market Cap: `${safe_float(token_data.get('market_cap')):,.0f}`
👥 Holders: `{safe_int(token_data.get('holders'))}`

━━━━━━━━━━━━━━━━━━

⚠️ *DECISÃO MANUAL*
❌ O bot NÃO compra.
❌ O bot NÃO vende.
👤 VOCÊ DECIDE.

🔗 [GMGN](https://gmgn.ai/sol/token/{token_address})
📊 [DexScreener](https://dexscreener.com/solana/{token_address})
"""
        send_telegram_message(message)
        print(f"[🚨 ALERTA] ${symbol} | Score: {score} | {wallet_name}")
        
    except Exception as e:
        print(f"[PROCESS] Erro: {e}")

# ============================================================
# TELEGRAM
# ============================================================
def send_telegram_message(message):
    try:
        bot.send_message(CHAT_ID, message, parse_mode="Markdown", disable_web_page_preview=True)
    except Exception as e:
        print(f"[TELEGRAM] Erro: {e}")

# ============================================================
# WEBHOOK
# ============================================================
@app.route('/webhook', methods=['POST'])
def webhook_handler():
    try:
        data = request.json
        if not data:
            return "No data", 200
        if isinstance(data, dict):
            data = [data]
        for event in data:
            process_transaction(event)
        return "OK", 200
    except Exception as e:
        print(f"[WEBHOOK] Erro: {e}")
        return "Error", 500

@app.route('/')
def health():
    return f"🐋 WHALE HUNTER v8.1 | {len(WALLET_ADDRESSES)} carteiras | Online"

# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    print(f"🐋 WHALE HUNTER v8.1")
    print(f"📊 Monitorando {len(WALLET_ADDRESSES)} carteiras")
    
    startup = f"""
🟢 *WHALE HUNTER v8.1 - ONLINE*

🐋 Monitorando {len(WALLET_ADDRESSES)} carteiras
🔍 Acumulação: {FILTERS['min_sm_buys']} compras em {FILTERS['sm_accumulation_window']//60} min
💰 Compra mínima: ${FILTERS['min_sm_buy_usd']}

✅ Alertas apenas para acumulação REAL!
"""
    send_telegram_message(startup)
    
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
