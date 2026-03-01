"""
server.py — Verifiable Wallet Transaction Explainer
70+ EVM chains, known token detection, direct API fallback for paid-tier chains.
USDC addresses from official Circle docs. USDT from official Tether deployments.
"""
import os
import json
import secrets
import traceback
import sys
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
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


# ══════════════════════════════════════════════════════════════
# KNOWN TOKENS — Official contract addresses
# All lowercase for matching. (name, decimals)
# ══════════════════════════════════════════════════════════════
KNOWN_TOKENS = {
    # ── Ethereum (1) ──
    "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": ("USDC", 6),
    "0xdac17f958d2ee523a2206206994597c13d831ec7": ("USDT", 6),
    "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2": ("WETH", 18),
    "0x6b175474e89094c44da98b954eedeac495271d0f": ("DAI", 18),
    "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599": ("WBTC", 8),
    "0x514910771af9ca656af840dff83e8264ecf986ca": ("LINK", 18),
    "0x1f9840a85d5af5bf1d1762f925bdaddc4201f984": ("UNI", 18),
    "0x95ad61b0a150d79219dcf64e1e6cc01f0b64c4ce": ("SHIB", 18),
    "0xae7ab96520de3a18e5e111b5eaab095312d7fe84": ("stETH", 18),
    "0xbe9895146f7af43049ca1c1ae358b0541ea49704": ("cbETH", 18),
    "0x7fc66500c84a76ad7e9c93437bfc5ac33e2ddae9": ("AAVE", 18),
    "0xd533a949740bb3306d119cc777fa900ba034cd52": ("CRV", 18),
    "0x5a98fcbea516cf06857215779fd812ca3bef1b32": ("LDO", 18),
    "0xc944e90c64b2c07662a292be6244bdf05cda44a7": ("GRT", 18),
    "0x4d224452801aced8b2f0aebe155379bb5d594381": ("APE", 18),
    # ── Base (8453) ──
    "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913": ("USDC", 6),
    "0xfde4c96c8593536e31f229ea8f37b2ada2699bb2": ("USDT", 6),
    "0x4200000000000000000000000000000000000006": ("WETH", 18),
    "0x50c5725949a6f0c72e6c4a641f24049a917db0cb": ("DAI", 18),
    "0xd9aaec86b65d86f6a7b5b1b0c42ffa531710b6ca": ("USDbC", 6),
    "0x2ae3f1ec7f1f5012cfeab0185bfc7aa3cf0dec22": ("cbETH", 18),
    # ── Arbitrum One (42161) ──
    "0xaf88d065e77c8cc2239327c5edb3a432268e5831": ("USDC", 6),
    "0xff970a61a04b1ca14834a43f5de4533ebddb5cc8": ("USDC.e", 6),
    "0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9": ("USDT", 6),
    "0x82af49447d8a07e3bd95bd0d56f35241523fbab1": ("WETH", 18),
    "0xda10009cbd5d07dd0cecc66161fc93d7c9000da1": ("DAI", 18),
    "0x2f2a2543b76a4166549f7aab2e75bef0aefc5b0f": ("WBTC", 8),
    # ── OP Mainnet (10) ──
    "0x0b2c639c533813f4aa9d7837caf62653d097ff85": ("USDC", 6),
    "0x7f5c764cbc14f9669b88837ca1490cca17c31607": ("USDC.e", 6),
    "0x94b008aa00579c1307b0ef2c499ad98a8ce58e58": ("USDT", 6),
    # ── Polygon (137) ──
    "0x3c499c542cef5e3811e1192ce70d8cc03d5c3359": ("USDC", 6),
    "0x2791bca1f2de4661ed88a30c99a7a9449aa84174": ("USDC.e", 6),
    "0xc2132d05d31c914a87c6611c10748aeb04b58e8f": ("USDT", 6),
    "0x7ceb23fd6bc0add59e62ac25578270cff1b9f619": ("WETH", 18),
    "0x0d500b1d8e8ef31e21c99d1db9a6444d3adf1270": ("WMATIC", 18),
    "0x8f3cf7ad23cd3cadbd9735aff958023239c6a063": ("DAI", 18),
    "0x1bfd67037b42cf73acf2047067bd4f2c47d9bfd6": ("WBTC", 8),
    # ── BNB Chain (56) ──
    "0x55d398326f99059ff775485246999027b3197955": ("USDT", 18),
    "0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d": ("USDC", 18),
    "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c": ("WBNB", 18),
    "0x1af3f329e8be154074d8769d1ffa4ee058b1dbc3": ("DAI", 18),
    "0x2170ed0880ac9a755fd29b2688956bd959f933f8": ("ETH", 18),
    "0x7130d2a12b9bcbfae4f2634d864a1ee1ce3ead9c": ("BTCB", 18),
    # ── Avalanche (43114) ──
    "0xb97ef9ef8734c71904d8002f8b6bc66dd9c48a6e": ("USDC", 6),
    "0x9702230a8ea53601f5cd2dc00fdbc13d4df4a8c7": ("USDT", 6),
    "0xb31f66aa3c1e785363f0875a1b74e27b85fd66c7": ("WAVAX", 18),
    "0x49d5c2bdffac6ce2bfdb6640f4f80f226bc10bab": ("WETH.e", 18),
    # ── Monad (143) ──
    "0x754704bc059f8c67012fed69bc8a327a5aafb603": ("USDC", 6),
    # ── Linea (59144) ──
    "0x176211869ca2b568f2a7d4ee941e073a821ee1ff": ("USDC", 6),
    "0xa219439258ca9da29e9cc4ce5596924745e12b93": ("USDT", 6),
    "0xe5d7c2a44ffddf6b295a15c148167daaaf5cf34f": ("WETH", 18),
    # ── Scroll (534352) ──
    "0x06efdbff2a14a7c8e15944d1f4a48f9f95f663a4": ("USDC", 6),
    "0xf55bec9cafdbe8730f096aa55dad6d22d44099df": ("USDT", 6),
    "0x5300000000000000000000000000000000000004": ("WETH", 18),
    # ── Blast (81457) ──
    "0x4300000000000000000000000000000000000003": ("USDB", 18),
    "0x4300000000000000000000000000000000000004": ("WETH", 18),
    # ── Sonic (146) ──
    "0x29219dd400f2bf60e5a23d13be72b486d4038894": ("USDC", 6),
    # ── Sei (1329) ──
    "0xe15fc38f6d8c56af07bbcbe3baf5708a2bf42392": ("USDC", 6),
    # ── HyperEVM (999) ──
    "0xb88339cb7199b77e23db6e890353e22632ba630f": ("USDC", 6),
    # ── Unichain (130) ──
    "0x078d782b760474a361dda0af3839290b0ef57ad6": ("USDC", 6),
    # ── World Chain (480) ──
    "0x79a02482a880bce3f13e09da970dc34db4cd24d1": ("USDC", 6),
    # ── Celo (42220) ──
    "0xceba9300f2b948710d2653dd7b07f33a8b32118c": ("USDC", 6),
    # ── XDC (50) ──
    "0xfa2958cb79b0491cc627c1557f441ef849ca8eb1": ("USDC", 6),
    # ── Mantle (5000) ──
    "0x09bc4e0d864854c6afb6eb9a9cdf58ac190d0df9": ("USDC", 6),
    "0x201eba5cc46d216ce6dc03f6a759e8e766e956ae": ("USDT", 6),
}


def resolve_token(address, raw_amount):
    """Resolve token name and format amount with correct decimals."""
    addr = address.lower()
    info = KNOWN_TOKENS.get(addr)
    if info:
        name, dec = info
        amt = raw_amount / (10 ** dec)
        if amt >= 1_000_000:
            return name, f"{amt:,.0f}"
        elif amt >= 0.01:
            return name, f"{amt:,.2f}"
        elif amt > 0:
            return name, f"{amt:.6f}"
        return name, "0"
    # Unknown token — try common decimals
    amt_6 = raw_amount / 1e6
    amt_18 = raw_amount / 1e18
    short = addr[:10] + "..."
    if 0.001 <= amt_6 <= 1e12 and raw_amount >= 1000:
        return short, f"{amt_6:,.2f}"
    elif 0.001 <= amt_18 <= 1e12:
        return short, f"{amt_18:,.4f}"
    return short, str(raw_amount)


# ══════════════════════════════════════════════════════════════
# CHAIN REGISTRY
# ══════════════════════════════════════════════════════════════

ETHERSCAN_KEY = os.environ.get("ETHERSCAN_API_KEY", "")

# Direct API chains — these have their own API endpoints
# Used as fallback when Etherscan V2 blocks paid-tier chains
DIRECT_CHAINS = [
    {"name": "Base",            "chainid": 8453,    "symbol": "ETH",  "explorer": "https://basescan.org",              "api": "https://api.basescan.org/api",             "testnet": False},
    {"name": "OP Mainnet",      "chainid": 10,      "symbol": "ETH",  "explorer": "https://optimistic.etherscan.io",   "api": "https://api-optimistic.etherscan.io/api",  "testnet": False},
    {"name": "BNB Smart Chain", "chainid": 56,      "symbol": "BNB",  "explorer": "https://bscscan.com",               "api": "https://api.bscscan.com/api",              "testnet": False},
    {"name": "Avalanche C",     "chainid": 43114,   "symbol": "AVAX", "explorer": "https://snowscan.xyz",              "api": "https://api.snowscan.xyz/api",             "testnet": False},
    {"name": "Base Sepolia",    "chainid": 84532,   "symbol": "ETH",  "explorer": "https://sepolia.basescan.org",      "api": "https://api-sepolia.basescan.org/api",     "testnet": True},
    {"name": "OP Sepolia",      "chainid": 11155420,"symbol": "ETH",  "explorer": "https://sepolia-optimistic.etherscan.io", "api": "https://api-sepolia-optimistic.etherscan.io/api", "testnet": True},
    {"name": "BNB Testnet",     "chainid": 97,      "symbol": "tBNB", "explorer": "https://testnet.bscscan.com",       "api": "https://api-testnet.bscscan.com/api",      "testnet": True},
    {"name": "Avalanche Fuji",  "chainid": 43113,   "symbol": "AVAX", "explorer": "https://testnet.snowscan.xyz",      "api": "https://api-testnet.snowscan.xyz/api",     "testnet": True},
]

# V2 API chains — use Etherscan V2 unified endpoint
V2_CHAINS = [
    {"name": "Ethereum",        "chainid": 1,        "symbol": "ETH",    "explorer": "https://etherscan.io",              "testnet": False},
    {"name": "Arbitrum One",    "chainid": 42161,    "symbol": "ETH",    "explorer": "https://arbiscan.io",               "testnet": False},
    {"name": "Polygon",         "chainid": 137,      "symbol": "POL",    "explorer": "https://polygonscan.com",           "testnet": False},
    {"name": "Linea",           "chainid": 59144,    "symbol": "ETH",    "explorer": "https://lineascan.build",           "testnet": False},
    {"name": "Blast",           "chainid": 81457,    "symbol": "ETH",    "explorer": "https://blastscan.io",              "testnet": False},
    {"name": "Scroll",          "chainid": 534352,   "symbol": "ETH",    "explorer": "https://scrollscan.com",            "testnet": False},
    {"name": "Mantle",          "chainid": 5000,     "symbol": "MNT",    "explorer": "https://mantlescan.xyz",            "testnet": False},
    {"name": "Celo",            "chainid": 42220,    "symbol": "CELO",   "explorer": "https://celoscan.io",               "testnet": False},
    {"name": "Gnosis",          "chainid": 100,      "symbol": "xDAI",   "explorer": "https://gnosisscan.io",             "testnet": False},
    {"name": "Fraxtal",         "chainid": 252,      "symbol": "frxETH", "explorer": "https://fraxscan.com",              "testnet": False},
    {"name": "Moonbeam",        "chainid": 1284,     "symbol": "GLMR",   "explorer": "https://moonbeam.moonscan.io",      "testnet": False},
    {"name": "Moonriver",       "chainid": 1285,     "symbol": "MOVR",   "explorer": "https://moonriver.moonscan.io",     "testnet": False},
    {"name": "opBNB",           "chainid": 204,      "symbol": "BNB",    "explorer": "https://opbnb.bscscan.com",         "testnet": False},
    {"name": "Fantom",          "chainid": 250,      "symbol": "FTM",    "explorer": "https://ftmscan.com",               "testnet": False},
    {"name": "Cronos",          "chainid": 25,       "symbol": "CRO",    "explorer": "https://cronoscan.com",             "testnet": False},
    {"name": "Taiko",           "chainid": 167000,   "symbol": "ETH",    "explorer": "https://taikoscan.io",              "testnet": False},
    {"name": "BitTorrent",      "chainid": 199,      "symbol": "BTT",    "explorer": "https://bttcscan.com",              "testnet": False},
    {"name": "XDC",             "chainid": 50,       "symbol": "XDC",    "explorer": "https://xdcscan.io",                "testnet": False},
    {"name": "ApeChain",        "chainid": 33139,    "symbol": "APE",    "explorer": "https://apescan.io",                "testnet": False},
    {"name": "World",           "chainid": 480,      "symbol": "ETH",    "explorer": "https://worldscan.org",             "testnet": False},
    {"name": "Sonic",           "chainid": 146,      "symbol": "S",      "explorer": "https://sonicscan.org",             "testnet": False},
    {"name": "Unichain",        "chainid": 130,      "symbol": "ETH",    "explorer": "https://uniscan.xyz",               "testnet": False},
    {"name": "Abstract",        "chainid": 2741,     "symbol": "ETH",    "explorer": "https://abscan.org",                "testnet": False},
    {"name": "Berachain",       "chainid": 80094,    "symbol": "BERA",   "explorer": "https://berascan.com",              "testnet": False},
    {"name": "Swellchain",      "chainid": 1923,     "symbol": "ETH",    "explorer": "https://swellscan.io",              "testnet": False},
    {"name": "Monad",           "chainid": 143,      "symbol": "MON",    "explorer": "https://monadscan.com",             "testnet": False},
    {"name": "HyperEVM",        "chainid": 999,      "symbol": "HYPE",   "explorer": "https://hyperscan.xyz",             "testnet": False},
    {"name": "Katana",          "chainid": 747474,   "symbol": "ETH",    "explorer": "https://katanascan.xyz",            "testnet": False},
    {"name": "Sei",             "chainid": 1329,     "symbol": "SEI",    "explorer": "https://seiscan.io",                "testnet": False},
    {"name": "zkSync Era",      "chainid": 324,      "symbol": "ETH",    "explorer": "https://explorer.zksync.io",        "testnet": False},
    {"name": "Polygon zkEVM",   "chainid": 1101,     "symbol": "ETH",    "explorer": "https://zkevm.polygonscan.com",     "testnet": False},
    {"name": "Memecore",        "chainid": 4352,     "symbol": "MEM",    "explorer": "https://memecorescan.io",           "testnet": False},
    {"name": "Stable",          "chainid": 988,      "symbol": "STB",    "explorer": "https://stablescan.xyz",            "testnet": False},
    {"name": "Plasma",          "chainid": 9745,     "symbol": "ETH",    "explorer": "https://plasmascan.io",             "testnet": False},
    {"name": "MegaETH",         "chainid": 4326,     "symbol": "ETH",    "explorer": "https://megaethscan.io",            "testnet": False},
    # ── Testnets ──
    {"name": "Sepolia",             "chainid": 11155111, "symbol": "ETH",  "explorer": "https://sepolia.etherscan.io",       "testnet": True},
    {"name": "Hoodi",               "chainid": 560048,   "symbol": "ETH",  "explorer": "https://hoodi.etherscan.io",         "testnet": True},
    {"name": "Arbitrum Sepolia",    "chainid": 421614,   "symbol": "ETH",  "explorer": "https://sepolia.arbiscan.io",        "testnet": True},
    {"name": "Polygon Amoy",        "chainid": 80002,    "symbol": "POL",  "explorer": "https://amoy.polygonscan.com",       "testnet": True},
    {"name": "Linea Sepolia",       "chainid": 59141,    "symbol": "ETH",  "explorer": "https://sepolia.lineascan.build",    "testnet": True},
    {"name": "Blast Sepolia",       "chainid": 168587773,"symbol": "ETH",  "explorer": "https://sepolia.blastscan.io",       "testnet": True},
    {"name": "Scroll Sepolia",      "chainid": 534351,   "symbol": "ETH",  "explorer": "https://sepolia.scrollscan.com",     "testnet": True},
    {"name": "Mantle Sepolia",      "chainid": 5003,     "symbol": "MNT",  "explorer": "https://sepolia.mantlescan.xyz",     "testnet": True},
    {"name": "Celo Sepolia",        "chainid": 11142220, "symbol": "CELO", "explorer": "https://sepolia.celoscan.io",        "testnet": True},
    {"name": "Fraxtal Hoodi",       "chainid": 2523,     "symbol": "frxETH","explorer": "https://hoodi.fraxscan.com",        "testnet": True},
    {"name": "Moonbase Alpha",      "chainid": 1287,     "symbol": "DEV",  "explorer": "https://moonbase.moonscan.io",       "testnet": True},
    {"name": "opBNB Testnet",       "chainid": 5611,     "symbol": "tBNB", "explorer": "https://testnet.opbnb.bscscan.com",  "testnet": True},
    {"name": "Taiko Hoodi",         "chainid": 167013,   "symbol": "ETH",  "explorer": "https://hoodi.taikoscan.io",         "testnet": True},
    {"name": "BitTorrent Test",     "chainid": 1029,     "symbol": "BTT",  "explorer": "https://testnet.bttcscan.com",       "testnet": True},
    {"name": "XDC Apothem",         "chainid": 51,       "symbol": "XDC",  "explorer": "https://apothem.xdcscan.io",         "testnet": True},
    {"name": "ApeChain Curtis",     "chainid": 33111,    "symbol": "APE",  "explorer": "https://curtis.apescan.io",          "testnet": True},
    {"name": "World Sepolia",       "chainid": 4801,     "symbol": "ETH",  "explorer": "https://sepolia.worldscan.org",      "testnet": True},
    {"name": "Sonic Testnet",       "chainid": 14601,    "symbol": "S",    "explorer": "https://testnet.sonicscan.org",      "testnet": True},
    {"name": "Unichain Sepolia",    "chainid": 1301,     "symbol": "ETH",  "explorer": "https://sepolia.uniscan.xyz",        "testnet": True},
    {"name": "Abstract Sepolia",    "chainid": 11124,    "symbol": "ETH",  "explorer": "https://sepolia.abscan.org",         "testnet": True},
    {"name": "Berachain Bepolia",   "chainid": 80069,    "symbol": "BERA", "explorer": "https://bepolia.berascan.com",       "testnet": True},
    {"name": "Swellchain Test",     "chainid": 1924,     "symbol": "ETH",  "explorer": "https://testnet.swellscan.io",       "testnet": True},
    {"name": "Monad Testnet",       "chainid": 10143,    "symbol": "MON",  "explorer": "https://testnet.monadscan.com",      "testnet": True},
    {"name": "Katana Bokuto",       "chainid": 737373,   "symbol": "ETH",  "explorer": "https://bokuto.katanascan.xyz",      "testnet": True},
    {"name": "Sei Testnet",         "chainid": 1328,     "symbol": "SEI",  "explorer": "https://testnet.seiscan.io",         "testnet": True},
    {"name": "Memecore Test",       "chainid": 43521,    "symbol": "MEM",  "explorer": "https://testnet.memecorescan.io",    "testnet": True},
    {"name": "Stable Testnet",      "chainid": 2201,     "symbol": "STB",  "explorer": "https://testnet.stablescan.xyz",     "testnet": True},
    {"name": "Plasma Testnet",      "chainid": 9746,     "symbol": "ETH",  "explorer": "https://testnet.plasmascan.io",      "testnet": True},
    {"name": "MegaETH Testnet",     "chainid": 6342,     "symbol": "ETH",  "explorer": "https://testnet.megaethscan.io",     "testnet": True},
]

ALL_CHAINS = DIRECT_CHAINS + V2_CHAINS

print(f"📡 {len(ALL_CHAINS)} chains | {len(KNOWN_TOKENS)} tokens", flush=True)


# ── Fetch helpers ────────────────────────────────────────────

def _http_get(url, timeout=8):
    """Simple HTTP GET returning parsed JSON."""
    req = urllib.request.Request(url, headers={"User-Agent": "WalletExplainer/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _parse_tx(result, receipt, chain):
    """Parse raw JSON-RPC tx + receipt into our standard format."""
    value_wei = int(result.get("value", "0x0"), 16)
    value_native = value_wei / 1e18
    gas_price_wei = int(result.get("gasPrice", "0x0"), 16)
    gas_price_gwei = gas_price_wei / 1e9
    block_number = int(result.get("blockNumber", "0x0"), 16)
    gas_used = int(receipt.get("gasUsed", "0x0"), 16) if receipt else int(result.get("gas", "0x0"), 16)
    status = "Success" if receipt and receipt.get("status") == "0x1" else "Failed"
    gas_fee = (gas_used * gas_price_wei) / 1e18
    symbol = chain["symbol"]

    # Parse ERC-20 token transfers from logs
    token_transfers = []
    transfer_topic = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
    for log in (receipt.get("logs", []) if receipt else []):
        topics = log.get("topics", [])
        if topics and topics[0] == transfer_topic and len(topics) >= 3:
            raw_amount = int(log.get("data", "0x0"), 16)
            token_name, formatted_amt = resolve_token(log.get("address", ""), raw_amount)
            token_transfers.append({
                "token": token_name,
                "amount": formatted_amt,
                "from": "0x" + topics[1][-40:],
                "to": "0x" + topics[2][-40:],
            })

    is_contract_call = result.get("input", "0x") != "0x"
    tx_hash = result.get("hash", "")

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
        "isTestnet": chain.get("testnet", False),
        "tokenTransfers": token_transfers[:10],
        "isContractCall": is_contract_call,
        "inputData": result.get("input", "0x")[:100],
        "nonce": int(result.get("nonce", "0x0"), 16),
    }


def _fetch_direct(tx_hash, chain):
    """Fetch from a chain's own explorer API (e.g. basescan.org/api)."""
    api_key = os.environ.get("BASESCAN_API_KEY", "") or ETHERSCAN_KEY or "YourApiKeyToken"
    try:
        data = _http_get(f"{chain['api']}?module=proxy&action=eth_getTransactionByHash&txhash={tx_hash}&apikey={api_key}")
        result = data.get("result")
        if not result or isinstance(result, str):
            return None
        data2 = _http_get(f"{chain['api']}?module=proxy&action=eth_getTransactionReceipt&txhash={tx_hash}&apikey={api_key}")
        return _parse_tx(result, data2.get("result") or {}, chain)
    except Exception:
        return None


def _fetch_v2(tx_hash, chain):
    """Fetch via Etherscan V2 unified API."""
    api_key = ETHERSCAN_KEY or "YourApiKeyToken"
    chainid = chain["chainid"]
    try:
        data = _http_get(
            f"https://api.etherscan.io/v2/api?chainid={chainid}"
            f"&module=proxy&action=eth_getTransactionByHash"
            f"&txhash={tx_hash}&apikey={api_key}"
        )
        result = data.get("result")
        if not result or result == "null" or isinstance(result, str):
            return None
        data2 = _http_get(
            f"https://api.etherscan.io/v2/api?chainid={chainid}"
            f"&module=proxy&action=eth_getTransactionReceipt"
            f"&txhash={tx_hash}&apikey={api_key}"
        )
        return _parse_tx(result, data2.get("result") or {}, chain)
    except Exception:
        return None


def fetch_real_transaction(tx_hash):
    """Search all chains in parallel to find the transaction."""
    print(f"📡 Searching across {len(ALL_CHAINS)} EVM chains...", flush=True)
    start = time.time()

    def check_chain(chain):
        try:
            if chain.get("api"):
                return _fetch_direct(tx_hash, chain)
            return _fetch_v2(tx_hash, chain)
        except Exception:
            return None

    # Batch 1: Priority — Direct API chains + first 10 V2 (major mainnets)
    batch1 = DIRECT_CHAINS + V2_CHAINS[:10]
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(check_chain, c): c for c in batch1}
        for f in as_completed(futures):
            result = f.result()
            if result:
                chain = futures[f]
                print(f"✅ Found on {chain['name']} in {time.time()-start:.1f}s", flush=True)
                return result

    # Batch 2: Remaining V2 chains (newer/smaller chains + all testnets)
    batch2 = V2_CHAINS[10:]
    if batch2:
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {pool.submit(check_chain, c): c for c in batch2}
            for f in as_completed(futures):
                result = f.result()
                if result:
                    chain = futures[f]
                    print(f"✅ Found on {chain['name']} in {time.time()-start:.1f}s", flush=True)
                    return result

    print(f"⚠️  Transaction not found on any chain ({time.time()-start:.1f}s)", flush=True)
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
        "isTestnet": False,
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
    is_testnet = tx_data.get("isTestnet", False)
    token_transfers = tx_data.get("tokenTransfers", [])

    tr_txt = ""
    if token_transfers:
        tr_txt = "\nToken transfers:\n" + "\n".join(
            [f"- {t['amount']} {t['token']} → {t['to'][:12]}..." for t in token_transfers]
        )

    prompt = f"""Explain this {'testnet ' if is_testnet else ''}transaction from **{chain_name}** simply.

Sections: SUMMARY, CHAIN{' (TESTNET=test money)' if is_testnet else ''}, DETAILS, TOKEN TRANSFERS, GAS FEES, SUSPICION CHECK

{"Smart contract call." if tx_data.get("isContractCall") else "Simple transfer."}
{tr_txt}

Explorer: {explorer_link}

Use ## headers, **bold**.

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

@app.route("/analyze-transaction", methods=["POST", "OPTIONS"])
def analyze_transaction():
    if request.method == "OPTIONS":
        return "", 200
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
                "isTestnet": tx_data.get("isTestnet", False),
                "tokenTransfers": tx_data.get("tokenTransfers", []),
            },
            "explanation": analysis["explanation"],
            "proof": analysis["proof"],
        })
    except Exception as e:
        print(f"❌ Route error: {e}", flush=True)
        traceback.print_exc()
        return jsonify({"error": "Something went wrong."}), 500


@app.route("/chains")
def chains_list():
    return jsonify({
        "total": len(ALL_CHAINS),
        "chains": [{"name": c["name"], "chainid": c["chainid"], "symbol": c["symbol"]} for c in ALL_CHAINS],
    })


@app.route("/debug")
def debug():
    pk = os.environ.get("OG_PRIVATE_KEY", "")
    has_key = bool(pk) and "YOUR" not in pk
    return jsonify({
        "sdk": OG_AVAILABLE,
        "key": f"{pk[:8]}..." if has_key else "NOT SET",
        "etherscan_key": "SET" if ETHERSCAN_KEY else "FREE TIER",
        "chains": len(ALL_CHAINS),
        "tokens": len(KNOWN_TOKENS),
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"🛡️  Server on http://0.0.0.0:{port} | SDK:{OG_AVAILABLE} | {len(ALL_CHAINS)} chains | {len(KNOWN_TOKENS)} tokens", flush=True)
    app.run(host="0.0.0.0", port=port, debug=False)
