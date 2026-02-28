"""
server.py — Verifiable Wallet Transaction Explainer
Flask backend using OpenGradient SDK for verifiable AI inference.
"""

import os
import json
import secrets
import traceback
import sys
import time
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

# Global client — reused across requests
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
        print(f"✅ OG client created (key: {private_key[:8]}...)", flush=True)
        try:
            _og_client.llm.ensure_opg_approval(opg_amount=5.0)
            print("✅ $OPG approval done", flush=True)
        except Exception as e:
            print(f"⚠️  Approval skipped: {e}", flush=True)
        return _og_client
    except Exception as e:
        print(f"❌ Client failed: {e}", flush=True)
        return None


# ── Transaction Data ─────────────────────────────────────────
def get_mock_transaction(tx_hash):
    return {
        "hash": tx_hash,
        "from": "0x71C7656EC7ab88b098defB751B7401B5f6d8976F",
        "to": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        "value": "1.5 ETH",
        "gasUsed": 21000,
        "gasPrice": "30 gwei",
        "gasFeeETH": f"{(21000 * 30) / 1e9:.6f} ETH",
        "blockNumber": 18923451,
        "status": "Success",
        "timestamp": "2025-01-15T10:30:00Z",
        "tokenTransfers": [
            {"token": "USDT", "amount": "200",
             "from": "0x71C7656EC7ab88b098defB751B7401B5f6d8976F",
             "to": "0xdAC17F958D2ee523a2206206994597C13D831ec7"},
            {"token": "WETH", "amount": "0.5",
             "from": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
             "to": "0x71C7656EC7ab88b098defB751B7401B5f6d8976F"},
        ],
    }


def get_mock_response(tx_data):
    gas_fee = tx_data.get("gasFeeETH", "0.000630 ETH")
    return {
        "explanation": f"""## Transaction Summary
This transaction was sent from wallet 0x71C7...976F to contract 0xA0b8...eB48.

## What Happened
The sender transferred **1.5 ETH** (Ethereum) to the receiving address. Additionally, two token transfers occurred:
- **200 USDT** (a stablecoin worth ~$200) was sent to address 0xdAC1...1ec7
- **0.5 WETH** (Wrapped Ether) was received back from the contract

This looks like a **token swap** — the user exchanged ETH/USDT for WETH through a smart contract (likely a decentralized exchange like Uniswap).

## Gas Fees
The transaction used **21,000 gas units** at a price of **30 gwei per unit**.
Total gas fee: **{gas_fee}** (roughly $1.20 at current prices).

## Suspicion Check
✅ **No suspicious patterns detected.**
- The gas fee is within normal range
- The addresses are not flagged
- The transaction pattern is consistent with a typical DEX swap""",
        "proof": {
            "paymentHash": "0x" + secrets.token_hex(32),
            "model": "GEMINI_2_5_FLASH (mock)",
            "verifiedByTEE": False,
            "explorerUrl": "https://explorer.opengradient.ai",
            "settlementNetwork": "Base Sepolia",
            "inferenceNetwork": "OpenGradient Testnet",
            "mode": "MOCK",
        },
    }


def call_opengradient(prompt, max_retries=3):
    """Call OpenGradient LLM with retries."""
    client = get_og_client()
    if client is None:
        return None

    for attempt in range(1, max_retries + 1):
        try:
            print(f"🚀 LLM attempt {attempt}/{max_retries}...", flush=True)
            start = time.time()

            result = client.llm.chat(
                model=og.TEE_LLM.GEMINI_2_5_FLASH,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a blockchain transaction analyst. Explain transactions clearly for beginners. Use markdown with ## headers and **bold**."
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=500,
                temperature=0.3,
            )

            elapsed = time.time() - start
            print(f"✅ LLM responded in {elapsed:.1f}s", flush=True)

            # Extract content
            explanation = None
            if hasattr(result, 'chat_output'):
                co = result.chat_output
                if isinstance(co, dict):
                    explanation = co.get("content", str(co))
                else:
                    explanation = str(co)

            payment_hash = getattr(result, "payment_hash", None)
            print(f"📦 Payment hash: {payment_hash}", flush=True)

            if explanation:
                return {
                    "explanation": explanation,
                    "payment_hash": payment_hash,
                }

        except Exception as e:
            elapsed = time.time() - start
            error_msg = str(e)
            print(f"❌ Attempt {attempt} failed ({elapsed:.1f}s): {error_msg}", flush=True)

            # If payment error, wait and retry
            if "payment" in error_msg.lower() and attempt < max_retries:
                wait = attempt * 2
                print(f"⏳ Retrying in {wait}s...", flush=True)
                time.sleep(wait)
                continue

            # Other errors — don't retry
            if "payment" not in error_msg.lower():
                break

    return None


def analyze_with_opengradient(tx_data):
    prompt = f"""You are a blockchain expert. Explain this transaction in simple, beginner-friendly English.

Break your answer into these sections:
1. SUMMARY — what happened in one sentence
2. DETAILS — where the funds went, who sent what to whom
3. GAS FEES — how much was paid in fees and what that means
4. SUSPICION CHECK — any suspicious patterns or is this normal

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

    return get_mock_response(tx_data)


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

        tx_data = get_mock_transaction(tx_hash)
        analysis = analyze_with_opengradient(tx_data)

        mode = analysis["proof"]["mode"]
        print(f"📤 Result: {mode}", flush=True)
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
                "tokenTransfers": tx_data["tokenTransfers"],
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
    """Quick status check."""
    pk = os.environ.get("OG_PRIVATE_KEY", "")
    has_key = bool(pk) and "YOUR" not in pk
    info = {
        "sdk": OG_AVAILABLE,
        "key": f"{pk[:8]}..." if has_key else "NOT SET",
    }
    if has_key and OG_AVAILABLE:
        try:
            client = og.Client(private_key=pk)
            info["client"] = "OK"
            try:
                r = client.llm.chat(
                    model=og.TEE_LLM.GEMINI_2_5_FLASH,
                    messages=[{"role": "user", "content": "Say OK"}],
                    max_tokens=5,
                )
                info["llm"] = "OK"
                info["response"] = str(r.chat_output)[:100]
                info["payment_hash"] = str(getattr(r, "payment_hash", None))
            except Exception as e:
                info["llm"] = f"FAIL: {e}"
        except Exception as e:
            info["client"] = f"FAIL: {e}"
    return jsonify(info)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"🛡️  Server on http://0.0.0.0:{port} | SDK:{OG_AVAILABLE}", flush=True)
    app.run(host="0.0.0.0", port=port, debug=False)
