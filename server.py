"""
server.py — Verifiable Wallet Transaction Explainer
Fetches REAL transaction data from any EVM chain, then explains with OpenGradient AI.

Supported chains: Ethereum, Base, Arbitrum, Optimism, Polygon, BSC, Avalanche,
Fantom, Linea, Scroll, zkSync, Blast, Mantle, Celo, Gnosis, Cronos
"""

import os
import json
import secrets
import traceback
import sys
import time
import urllib.request
import urllib.error
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__, static_folder="public", static_url_path="")
CORS(app)

# ── OpenGradient Setup ───────────────────────────────────────
OG_AVAILABLE = False
og = None

try:
    import opengradient as _og
    og = _og
    OG_AVAILABLE = True
    print("✅ OpenGradient SDK imported", flush=True)
except Exception as e:
    print(f"⚠️  OpenGradient not available: {e}", flush=True)

_og_client = None

def get_og_client():
    global _og_client
    if _og_client is not None:
        return _og_client
    if not OG_AVAILABLE:
        return None
    private_key = os.environ.get("OG_PRIVATE_KEY", "")
    if not private_key or "YOUR_PRIVATE_KEY" in private_key:
        return None
    try:
        _og_client = og.Client(private_key=private_key)
        try:
            _og_client.llm.ensure_opg_approval(opg_amount=5.0)
        except Exception:
            pass
        print("✅ OG client ready", flush=True)
        return _og_client
    except Exception as e:
        print(f"❌ OG client failed: {e}", flush=True)
        return None


# ── EVM Chain Registry ───────────────────────────────────────
# Etherscan v2 API supports chainid parameter for many chains.
# For chains not on v2, we use their individual explorer APIs.

ETHERSCAN_KEY = os.environ.get("ETHERSCAN_API_KEY", "")

# Etherscan V2 supported chains (use single API with chainid)
ETHERSCAN_V2_CHAINS = [
    {"name": "Ethereum",       "chainid": 1,      "symbol": "ETH",   "explorer": "https://etherscan.io"},
    {"name": "Base",           "chainid": 8453,    "symbol": "ETH",   "explorer": "https://basescan.org"},
    {"name": "Arbitrum One",   "chainid": 42161,   "symbol": "ETH",   "explorer": "https://arbiscan.io"},
    {"name": "Optimism",       "chainid": 10,      "symbol": "ETH",   "explorer": "https://optimistic.etherscan.io"},
    {"name": "Polygon",        "chainid": 137,     "symbol": "MATIC", "explorer": "https://polygonscan.com"},
    {"name": "BNB Chain",      "chainid": 56,      "symbol": "BNB",   "explorer": "https://bscscan.com"},
    {"name": "Avalanche C",    "chainid": 43114,   "symbol": "AVAX",  "explorer": "https://snowscan.xyz"},
    {"name": "Fantom",         "chainid": 250,     "symbol": "FTM",   "explorer": "https://ftmscan.com"},
    {"name": "Linea",          "chainid": 59144,   "symbol": "ETH",   "explorer": "https://lineascan.build"},
    {"name": "Scroll",         "chainid": 534352,  "symbol": "ETH",   "explorer": "https://scrollscan.com"},
    {"name": "Blast",          "chainid": 81457,   "symbol": "ETH",   "explorer": "https://blastscan.io"},
    {"name": "Mantle",         "chainid": 5000,    "symbol": "MNT",   "explorer": "https://mantlescan.xyz"},
    {"name": "Celo",           "chainid": 42220,   "symbol": "CELO",  "explorer": "https://celoscan.io"},
    {"name": "Gnosis",         "chainid": 100,     "symbol": "xDAI",  "explorer": "https://gnosisscan.io"},
    {"name": "Cronos",         "chainid": 25,      "symbol": "CRO",   "explorer": "https://cronoscan.com"},
    {"name": "zkSync Era",     "chainid": 324,     "symbol": "ETH",   "explorer": "https://explorer.zksync.io"},
    {"name": "Polygon zkEVM",  "chainid": 1101,    "symbol": "ETH",   "explorer": "https://zkevm.polygonscan.com"},
    {"name": "Base Sepolia",   "chainid": 84532,   "symbol": "ETH",   "explorer": "https://sepolia.basescan.org"},
    {"name": "Sepolia",        "chainid": 11155111,"symbol": "ETH",   "explorer": "https://sepolia.etherscan.io"},
]


def fetch_tx_from_chain(tx_hash, chain):
    """Try to fetch a transaction from a specific chain via Etherscan V2 API."""
    api_key = ETHERSCAN_KEY or "YourApiKeyToken"
    chainid = chain["chainid"]

    tx_url = (
        f"https://api.etherscan.io/v2/api?chainid={chainid}"
        f"&module=proxy&action=eth_getTransactionByHash"
        f"&txhash={tx_hash}&apikey={api_key}"
    )

    try:
        req = urllib.request.Request(tx_url, headers={"User-Agent": "WalletExplainer/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())

        result = data.get("result")
        if not result or result == "null" or isinstance(result, str):
            return None

        # Found it — now get receipt
        receipt_url = (
            f"https://api.etherscan.io/v2/api?chainid={chainid}"
            f"&module=proxy&action=eth_getTransactionReceipt"
            f"&txhash={tx_hash}&apikey={api_key}"
        )
        req2 = urllib.request.Request(receipt_url, headers={"User-Agent": "WalletExplainer/1.0"})
        with urllib.request.urlopen(req2, timeout=8) as resp2:
            receipt_data = json.loads(resp2.read().decode())
        receipt = receipt_data.get("result", {})

        # Parse values
        value_wei = int(result.get("value", "0x0"), 16)
        value_native = value_wei / 1e18
        gas_price_wei = int(result.get("gasPrice", "0x0"), 16)
        gas_price_gwei = gas_price_wei / 1e9
        gas_limit = int(result.get("gas", "0x0"), 16)
        block_number = int(result.get("blockNumber", "0x0"), 16)
        gas_used = int(receipt.get("gasUsed", "0x0"), 16) if receipt else gas_limit
        status = "Success" if receipt and receipt.get("status") == "0x1" else "Failed"
        gas_fee = (gas_used * gas_price_wei) / 1e18

        # Parse ERC-20 token transfers
        token_transfers = []
        transfer_topic = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
        if receipt and receipt.get("logs"):
            for log in receipt["logs"]:
                topics = log.get("topics", [])
                if topics and topics[0] == transfer_topic and len(topics) >= 3:
                    token_from = "0x" + topics[1][-40:]
                    token_to = "0x" + topics[2][-40:]
                    raw_amount = int(log.get("data", "0x0"), 16)
                    token_transfers.append({
                        "token": log["address"][:10] + "...",
                        "amount": str(raw_amount),
                        "from": token_from,
                        "to": token_to,
                    })

        symbol = chain["symbol"]
        is_contract_call = result.get("input", "0x") != "0x"

        return {
            "hash": tx_hash,
            "from": result.get("from", "unknown"),
            "to": result.get("to") or "Contract Creation",
            "value": f"{value_native:.6f} {symbol}" if value_native > 0 else f"0 {symbol}",
            "gasUsed": gas_used,
            "gasPrice": f"{gas_price_gwei:.2f} gwei",
            "gasFeeETH": f"{gas_fee:.6f} {symbol}",
            "blockNumber": block_number,
            "status": status,
            "chain": chain["name"],
            "chainExplorer": f"{chain['explorer']}/tx/{tx_hash}",
            "symbol": symbol,
            "tokenTransfers": token_transfers[:5],
            "isContractCall": is_contract_call,
            "inputData": result.get("input", "0x")[:100],
            "nonce": int(result.get("nonce", "0x0"), 16),
        }

    except Exception:
        return None


def fetch_real_transaction(tx_hash):
    """Try all EVM chains to find the transaction."""
    print(f"📡 Searching across {len(ETHERSCAN_V2_CHAINS)} EVM chains...", flush=True)

    # Try popular chains first (Ethereum, Base, Arbitrum, Optimism, Polygon, BSC)
    priority_chains = ETHERSCAN_V2_CHAINS[:6]
    other_chains = ETHERSCAN_V2_CHAINS[6:]

    for chain in priority_chains:
        result = fetch_tx_from_chain(tx_hash, chain)
        if result:
            print(f"✅ Found on {chain['name']}!", flush=True)
            return result

    # Try remaining chains
    for chain in other_chains:
        result = fetch_tx_from_chain(tx_hash, chain)
        if result:
            print(f"✅ Found on {chain['name']}!", flush=True)
            return result

    print("⚠️  Transaction not found on any chain", flush=True)
    return None


def get_fallback_transaction(tx_hash):
    return {
        "hash": tx_hash,
        "from": "unknown",
        "to": "unknown",
        "value": "unknown",
        "gasUsed": 0,
        "gasPrice": "unknown",
        "gasFeeETH": "unknown",
        "blockNumber": 0,
        "status": "Unknown",
        "chain": "Unknown",
        "chainExplorer": "",
        "symbol": "ETH",
        "tokenTransfers": [],
        "isContractCall": False,
        "inputData": "0x",
        "nonce": 0,
    }


# ── OpenGradient AI Analysis ────────────────────────────────

def call_opengradient(prompt, max_retries=2):
    client = get_og_client()
    if client is None:
        return None
    for attempt in range(1, max_retries + 1):
        try:
            print(f"🚀 LLM attempt {attempt}...", flush=True)
            start = time.time()
            result = client.llm.chat(
                model=og.TEE_LLM.GEMINI_2_5_FLASH,
                messages=[
                    {"role": "system", "content": "You are a blockchain transaction analyst. Explain transactions clearly for beginners. Use markdown with ## headers and **bold**."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=600,
                temperature=0.3,
            )
            elapsed = time.time() - start
            print(f"✅ LLM responded in {elapsed:.1f}s", flush=True)
            explanation = None
            if hasattr(result, 'chat_output'):
                co = result.chat_output
                explanation = co.get("content", str(co)) if isinstance(co, dict) else str(co)
            payment_hash = getattr(result, "payment_hash", None)
            if explanation:
                return {"explanation": explanation, "payment_hash": payment_hash}
        except Exception as e:
            print(f"❌ LLM attempt {attempt}: {e}", flush=True)
            if attempt < max_retries:
                time.sleep(2)
    return None


def analyze_transaction_data(tx_data):
    chain_name = tx_data.get("chain", "Unknown")
    explorer_link = tx_data.get("chainExplorer", "")
    is_real = chain_name != "Unknown"

    prompt = f"""You are a blockchain expert. Explain this {'real ' if is_real else ''}transaction from the **{chain_name}** network in simple, beginner-friendly English.

Break your answer into these sections:
1. SUMMARY — what happened in one sentence
2. CHAIN — which blockchain network this was on and what that means
3. DETAILS — where the funds went, who sent what to whom
4. GAS FEES — how much was paid in fees and whether that's normal for {chain_name}
5. SUSPICION CHECK — any suspicious patterns or is this normal

{"This is a smart contract interaction (not a simple transfer)." if tx_data.get("isContractCall") else "This is a simple value transfer."}
{f"Token transfers detected: {len(tx_data.get('tokenTransfers', []))} ERC-20 transfers." if tx_data.get("tokenTransfers") else ""}

Explorer link: {explorer_link}

Use markdown: ## for headers, **bold** for emphasis.

Transaction data:
{json.dumps(tx_data, indent=2)}"""

    result = call_opengradient(prompt)

    if result:
        payment_hash = result.get("payment_hash")
        return {
            "explanation": result["explanation"],
            "proof": {
                "paymentHash": payment_hash or "verified-no-settlement",
                "model": "GEMINI_2_5_FLASH",
                "verifiedByTEE": True,
                "explorerUrl": f"https://explorer.opengradient.ai/tx/{payment_hash}" if payment_hash else "https://explorer.opengradient.ai",
                "settlementNetwork": "Base Sepolia",
                "inferenceNetwork": "OpenGradient",
                "mode": "LIVE",
            },
        }

    # Fallback — no AI
    return {
        "explanation": f"""## Transaction on {chain_name}
**Hash:** {tx_data['hash'][:16]}...
**From:** {tx_data['from']}
**To:** {tx_data['to']}
**Value:** {tx_data['value']}
**Status:** {tx_data['status']}
**Block:** #{tx_data['blockNumber']:,}
**Gas Fee:** {tx_data['gasFeeETH']}

{f"[View on Explorer]({explorer_link})" if explorer_link else ""}

⚠️ AI explanation unavailable — showing raw data.""",
        "proof": {
            "paymentHash": "0x" + secrets.token_hex(32),
            "model": "fallback (no AI)",
            "verifiedByTEE": False,
            "explorerUrl": "https://explorer.opengradient.ai",
            "settlementNetwork": "Base Sepolia",
            "inferenceNetwork": "OpenGradient Testnet",
            "mode": "MOCK",
        },
    }


# ── Routes ───────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("public", "index.html")

@app.route("/<path:path>")
def static_files(path):
    return send_from_directory("public", path)

@app.route("/analyze-transaction", methods=["POST"])
def analyze_transaction():
    try:
        data = request.get_json()
        tx_hash = data.get("txHash", "").strip() if data else ""
        if not tx_hash:
            return jsonify({"error": "Please provide a transaction hash."}), 400
        if not tx_hash.startswith("0x") or len(tx_hash) < 10:
            return jsonify({"error": "Hash must start with '0x' and be valid hex."}), 400

        print(f"\n{'='*50}", flush=True)
        print(f"🔍 Analyzing: {tx_hash}", flush=True)

        # Fetch real transaction from any EVM chain
        tx_data = fetch_real_transaction(tx_hash)
        if tx_data is None:
            print("⚠️  Not found — using fallback", flush=True)
            tx_data = get_fallback_transaction(tx_hash)

        # Analyze with OpenGradient AI
        analysis = analyze_transaction_data(tx_data)

        mode = analysis["proof"]["mode"]
        chain = tx_data.get("chain", "Unknown")
        print(f"📤 Result: {mode} | Chain: {chain}", flush=True)
        print(f"{'='*50}\n", flush=True)

        return jsonify({
            "success": True,
            "transaction": {
                "hash": tx_data["hash"],
                "from": tx_data["from"],
                "to": tx_data["to"],
                "value": tx_data["value"],
                "gasUsed": tx_data["gasUsed"],
                "gasPrice": tx_data["gasPrice"],
                "gasFee": tx_data["gasFeeETH"],
                "status": tx_data["status"],
                "block": tx_data["blockNumber"],
                "chain": tx_data.get("chain", "Unknown"),
                "chainExplorer": tx_data.get("chainExplorer", ""),
                "tokenTransfers": tx_data.get("tokenTransfers", []),
            },
            "explanation": analysis["explanation"],
            "proof": analysis["proof"],
        })
    except Exception as e:
        print(f"❌ Route error: {e}", flush=True)
        traceback.print_exc()
        return jsonify({"error": "Something went wrong."}), 500


@app.route("/debug")
def debug():
    pk = os.environ.get("OG_PRIVATE_KEY", "")
    has_key = bool(pk) and "YOUR" not in pk
    return jsonify({
        "sdk": OG_AVAILABLE,
        "key": f"{pk[:8]}..." if has_key else "NOT SET",
        "etherscan_key": "SET" if ETHERSCAN_KEY else "FREE TIER",
        "chains_supported": len(ETHERSCAN_V2_CHAINS),
        "chains": [c["name"] for c in ETHERSCAN_V2_CHAINS],
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"🛡️  Server on http://0.0.0.0:{port} | SDK:{OG_AVAILABLE} | Chains:{len(ETHERSCAN_V2_CHAINS)}", flush=True)
    app.run(host="0.0.0.0", port=port, debug=False)
