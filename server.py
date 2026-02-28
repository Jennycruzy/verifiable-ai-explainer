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


def create_og_client():
    """Create a fresh OpenGradient client each time to avoid stale state."""
    if not OG_AVAILABLE:
        print("⚠️  [create_client] SDK not available", flush=True)
        return None

    private_key = os.environ.get("OG_PRIVATE_KEY", "")
    if not private_key or "YOUR_PRIVATE_KEY" in private_key:
        print("⚠️  [create_client] No valid OG_PRIVATE_KEY", flush=True)
        return None

    print(f"🔑 [create_client] Key found: {private_key[:8]}...", flush=True)

    try:
        client = og.Client(private_key=private_key)
        print("✅ [create_client] Client created", flush=True)
        return client
    except Exception as e:
        print(f"❌ [create_client] Failed: {e}", flush=True)
        traceback.print_exc()
        return None


def try_opg_approval(client):
    """Try to approve $OPG spending. Non-fatal if it fails."""
    try:
        client.llm.ensure_opg_approval(opg_amount=5.0)
        print("✅ [approval] $OPG approved", flush=True)
        return True
    except Exception as e:
        print(f"⚠️  [approval] Skipped: {e}", flush=True)
        return False


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
    """Return mock analysis."""
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


def analyze_with_opengradient(tx_data):
    """Attempt real OpenGradient inference, fall back to mock."""

    prompt = f"""You are a blockchain expert. Explain this transaction in simple, beginner-friendly English.

Break your answer into these sections:
1. SUMMARY — what happened in one sentence
2. DETAILS — where the funds went, who sent what to whom
3. GAS FEES — how much was paid in fees and what that means
4. SUSPICION CHECK — any suspicious patterns or is this normal

Use markdown: ## for headers, **bold** for emphasis.

Transaction data:
{json.dumps(tx_data, indent=2)}"""

    # Step 1: Create client
    print("\n── OpenGradient Analysis ──", flush=True)
    client = create_og_client()
    if client is None:
        print("⬇️  No client, using mock", flush=True)
        return get_mock_response(tx_data)

    # Step 2: Try approval (non-fatal)
    try_opg_approval(client)

    # Step 3: Call LLM
    print("🚀 [llm] Calling GEMINI_2_5_FLASH...", flush=True)
    start_time = time.time()

    try:
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

        elapsed = time.time() - start_time
        print(f"✅ [llm] Response received in {elapsed:.1f}s", flush=True)

        # Extract response
        explanation = None
        payment_hash = None

        # Try different response formats
        if hasattr(result, 'chat_output'):
            chat_output = result.chat_output
            print(f"📦 [llm] chat_output type: {type(chat_output)}", flush=True)
            print(f"📦 [llm] chat_output: {str(chat_output)[:200]}", flush=True)

            if isinstance(chat_output, dict):
                explanation = chat_output.get("content", str(chat_output))
            elif isinstance(chat_output, str):
                explanation = chat_output
            else:
                explanation = str(chat_output)

        if hasattr(result, 'payment_hash'):
            payment_hash = result.payment_hash
            print(f"🔗 [llm] payment_hash: {payment_hash}", flush=True)

        # Log all attributes for debugging
        print(f"📦 [llm] result attributes: {dir(result)}", flush=True)

        if explanation:
            print(f"✅ [llm] LIVE MODE SUCCESS", flush=True)
            return {
                "explanation": explanation,
                "proof": {
                    "paymentHash": payment_hash or "pending-settlement",
                    "model": "GEMINI_2_5_FLASH",
                    "verifiedByTEE": True,
                    "explorerUrl": f"https://explorer.opengradient.ai/tx/{payment_hash}" if payment_hash else "https://explorer.opengradient.ai",
                    "settlementNetwork": "Base Sepolia",
                    "inferenceNetwork": "OpenGradient",
                    "mode": "LIVE",
                },
            }
        else:
            print("⚠️  [llm] No explanation extracted from response", flush=True)
            print(f"📦 [llm] Full result: {result}", flush=True)

    except Exception as e:
        elapsed = time.time() - start_time
        print(f"❌ [llm] FAILED after {elapsed:.1f}s: {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()

    print("⬇️  Falling back to mock", flush=True)
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
        print(f"🔍 Request: {tx_hash}", flush=True)

        tx_data = get_mock_transaction(tx_hash)
        analysis = analyze_with_opengradient(tx_data)

        mode = analysis["proof"].get("mode", "?")
        print(f"📤 Response mode: {mode}", flush=True)
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


# ── Debug endpoint ───────────────────────────────────────────

@app.route("/debug")
def debug():
    """Quick check of OpenGradient status."""
    private_key = os.environ.get("OG_PRIVATE_KEY", "")
    has_key = bool(private_key) and "YOUR_PRIVATE_KEY" not in private_key

    info = {
        "og_sdk_available": OG_AVAILABLE,
        "og_private_key_set": has_key,
        "og_key_prefix": private_key[:8] + "..." if has_key else "NOT SET",
        "port": os.environ.get("PORT", "not set"),
    }

    if has_key and OG_AVAILABLE:
        try:
            client = og.Client(private_key=private_key)
            info["client_created"] = True

            # Quick test — just try a short completion
            try:
                result = client.llm.chat(
                    model=og.TEE_LLM.GEMINI_2_5_FLASH,
                    messages=[{"role": "user", "content": "Say OK"}],
                    max_tokens=10,
                )
                info["llm_test"] = "SUCCESS"
                info["llm_response"] = str(result.chat_output)[:100]
                info["payment_hash"] = str(getattr(result, "payment_hash", None))
            except Exception as e:
                info["llm_test"] = f"FAILED: {e}"

        except Exception as e:
            info["client_created"] = False
            info["client_error"] = str(e)

    return jsonify(info)


# ── Start ────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"\n🛡️  Server starting on http://0.0.0.0:{port}", flush=True)
    print(f"🔧 OG SDK: {OG_AVAILABLE}", flush=True)
    print(f"🔑 Key set: {bool(os.environ.get('OG_PRIVATE_KEY'))}", flush=True)
    sys.stdout.flush()
    app.run(host="0.0.0.0", port=port, debug=False)
